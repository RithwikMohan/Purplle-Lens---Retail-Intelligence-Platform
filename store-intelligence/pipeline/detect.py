import os
import sys
import cv2
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import numpy as np

# Adjust path to import app modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from tracker import PersonFeatureExtractor, ReIDTrackerManager
from emit import EventEmitter

# Try importing ultralytics (YOLO)
try:
    import torch
    # Monkeypatch torch.load to bypass weights_only=True default in PyTorch 2.6+ for YOLOv8 loading compatibility
    _orig_torch_load = torch.load
    def _patched_torch_load(*args, **kwargs):
        if "weights_only" not in kwargs:
            kwargs["weights_only"] = False
        return _orig_torch_load(*args, **kwargs)
    torch.load = _patched_torch_load

    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except Exception as e:
    YOLO_AVAILABLE = False
    print(f"WARNING: ultralytics (YOLOv8) could not be loaded ({e}). Pipeline will run in simulation mode.")

class StoreIntelligencePipeline:
    """
    Main pipeline to process store CCTV clips.
    Loads YOLOv8, tracks people, detects staff, runs cross-camera Re-ID,
    and formats behavioral events into a JSONL stream.
    """
    def __init__(self, 
                 store_id: str, 
                 video_dir: str, 
                 output_jsonl: str = "events_output.jsonl",
                 frame_skip: int = 15,
                 staff_color: str = "black"):
        self.store_id = store_id
        self.video_dir = video_dir
        self.frame_skip = frame_skip
        self.staff_color = staff_color  # 'black' for Store 1, 'purple' for Store 2
        
        # Clear output JSONL file from previous run if exists
        if os.path.exists(output_jsonl):
            os.remove(output_jsonl)
            
        # Initialize ReID Manager and Event Emitter
        self.tracker_manager = ReIDTrackerManager()
        self.emitter = EventEmitter(output_jsonl)
        
        # Load YOLO model
        if YOLO_AVAILABLE:
            # We use YOLOv8 Nano for fast CPU execution
            self.model = YOLO("yolov8n.pt")
        else:
            self.model = None

        # Track state metrics
        self.active_tracks: Dict[str, Dict[int, List[Tuple[float, float, datetime]]]] = {}
        # Stores visitor session sequences count: visitor_id -> count of events
        self.session_sequences: Dict[str, int] = {}
        
        # Sim baseline start datetime for events (e.g. 2026-03-08 18:10:00)
        self.base_time = datetime(2026, 3, 8, 18, 10, 0)

    def get_session_seq(self, visitor_id: str) -> int:
        self.session_sequences[visitor_id] = self.session_sequences.get(visitor_id, 0) + 1
        return self.session_sequences[visitor_id]

    def define_zones(self, camera_name: str, width: int, height: int) -> Dict[str, Tuple[int, int, int, int]]:
        """
        Defines zone coordinate boundaries (x1, y1, x2, y2) relative to frame resolution.
        """
        zones = {}
        cname = camera_name.lower()
        if "billing" in cname or "cam 5" in cname:
            zones["BILLING_ZONE"] = (int(width * 0.1), int(height * 0.1), int(width * 0.9), int(height * 0.9))
        elif "zone" in cname or "cam 1" in cname or "cam 2" in cname:
            # Define product sections on left/right/center of screen
            zones["SKINCARE"] = (0, 0, int(width * 0.4), int(height * 0.8))
            zones["MOISTURISER"] = (int(width * 0.4), 0, int(width * 0.7), int(height * 0.8))
            zones["LIPSTICK"] = (int(width * 0.7), 0, width, int(height * 0.8))
        return zones

    def get_matched_zone(self, cx: int, cy: int, zones: Dict[str, Tuple[int, int, int, int]]) -> Optional[str]:
        for zone_id, bbox in zones.items():
            x1, y1, x2, y2 = bbox
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return zone_id
        return None

    def process_video_file(self, video_path: str, camera_id: str):
        """
        Processes a single video clip. Tracks bounding boxes, runs Re-ID,
        and triggers entry/exit/dwell events.
        """
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            return
            
        print(f"Processing video: {video_path} (Camera: {camera_id})")
        
        cap = cv2.VideoCapture(video_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 15
        
        zones = self.define_zones(camera_id, width, height)
        
        frame_idx = 0
        active_visitors_in_billing = set()
        
        # Track history mapping: track_id -> (last_zone_id, enter_time, dwell_emitted)
        track_states = {}
        
        # Local per-frame staff vote accumulator: track_id -> count of frames detected as staff
        # Used instead of the global profile is_staff to avoid cross-camera contamination.
        local_track_staff_votes: Dict[int, int] = {}
        local_track_frame_count: Dict[int, int] = {}

        if self.model is None:
            # Run simulation mode if YOLO is not installed (e.g. environment fallback)
            self._run_simulation(camera_id, zones)
            cap.release()
            return

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            # Process only every N-th frame to speed up CPU tracking
            if frame_idx % self.frame_skip != 0:
                frame_idx += 1
                continue
                
            # Frame offset calculation
            frame_offset_seconds = frame_idx / fps
            timestamp = self.base_time + timedelta(seconds=frame_offset_seconds)
            
            # Predict & track using YOLOv8
            # classes=0 is 'person' in COCO dataset
            results = self.model.track(frame, persist=True, classes=0, verbose=False, device="cpu")
            
            if results and results[0].boxes and results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                confs = results[0].boxes.conf.cpu().numpy()
                
                for bbox, track_id, conf in zip(boxes, track_ids, confs):
                    # 1. Uniform color check for staff classification (local, per-frame)
                    local_is_staff = PersonFeatureExtractor.check_is_staff(frame, bbox, self.staff_color)
                    
                    # 2. Extract HSV color histogram for Re-ID matching
                    hsv_hist = PersonFeatureExtractor.extract_color_histogram(frame, bbox)
                    
                    # 3. Associate local track with global visitor ID
                    visitor_id = self.tracker_manager.associate_track(
                        camera_id, track_id, timestamp, hsv_hist, local_is_staff
                    )
                    
                    # 4. Save visitor image crop for dashboard
                    img_path = f"images/{self.store_id}_{visitor_id}.jpg"
                    if not os.path.exists(img_path) and "entry" in camera_id.lower():
                        # Only capture from entry cameras for a clean frontal/profile view
                        os.makedirs("images", exist_ok=True)
                        h, w = frame.shape[:2]
                        x1, y1, x2, y2 = bbox
                        px, py = 10, 10
                        crop = frame[max(0, y1-py):min(h, y2+py), max(0, x1-px):min(w, x2+px)]
                        if crop.size > 0:
                            cv2.imwrite(img_path, crop)
                    
                    # Accumulate local staff votes for this track (per-camera, avoids cross-camera bleed)
                    local_track_staff_votes[track_id] = local_track_staff_votes.get(track_id, 0) + (1 if local_is_staff else 0)
                    local_track_frame_count[track_id] = local_track_frame_count.get(track_id, 0) + 1
                    
                    # Use local frame detection for downstream event logic
                    is_staff = local_is_staff
                    
                    cx, cy = int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)
                    
                    # Store track coordinates
                    self.active_tracks.setdefault(camera_id, {}).setdefault(track_id, []).append((cx, cy, timestamp))
                    
                    # Event detection logic based on camera angle type
                    c_id_lower = camera_id.lower()
                    if "entry" in c_id_lower:
                        # For entry cameras we defer event emission to end-of-video (two-pass).
                        # Just accumulate track data here; see post-loop section below.
                        pass
                        

                    elif "billing" in c_id_lower:
                        # Billing counter logic
                        in_billing = self.get_matched_zone(cx, cy, zones) == "BILLING_ZONE"
                        
                        if in_billing and track_id not in active_visitors_in_billing:
                            active_visitors_in_billing.add(track_id)
                            # Queue depth matches other active shoppers currently in billing queue
                            q_depth = len(active_visitors_in_billing)
                            self.emitter.emit(
                                store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                                event_type="BILLING_QUEUE_JOIN", timestamp=timestamp, is_staff=is_staff,
                                confidence=conf, queue_depth=q_depth, session_seq=self.get_session_seq(visitor_id)
                            )
                        elif not in_billing and track_id in active_visitors_in_billing:
                            active_visitors_in_billing.remove(track_id)
                            # Emitters for queue exits are processed by API or simple exit rules
                            
                    elif "zone" in c_id_lower:
                        # Product shelves logic: track zone entries, exits, and dwell times
                        current_zone = self.get_matched_zone(cx, cy, zones)
                        last_zone, enter_time, dwell_emitted = track_states.get(track_id, (None, None, False))
                        
                        if current_zone != last_zone:
                            # 1. Exit old zone
                            if last_zone:
                                dwell_ms = int((timestamp - enter_time).total_seconds() * 1000.0)
                                self.emitter.emit(
                                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                                    event_type="ZONE_EXIT", timestamp=timestamp, zone_id=last_zone,
                                    dwell_ms=dwell_ms, is_staff=is_staff, confidence=conf,
                                    session_seq=self.get_session_seq(visitor_id)
                                )
                            # 2. Enter new zone
                            if current_zone:
                                self.emitter.emit(
                                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                                    event_type="ZONE_ENTER", timestamp=timestamp, zone_id=current_zone,
                                    is_staff=is_staff, confidence=conf, session_seq=self.get_session_seq(visitor_id)
                                )
                                track_states[track_id] = (current_zone, timestamp, False)
                            else:
                                track_states[track_id] = (None, None, False)
                        elif current_zone and last_zone == current_zone:
                            # 3. Continuous Dwell check: 30+ seconds
                            dwell_duration = (timestamp - enter_time).total_seconds()
                            if dwell_duration >= 30.0 and not dwell_emitted:
                                self.emitter.emit(
                                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                                    event_type="ZONE_DWELL", timestamp=timestamp, zone_id=current_zone,
                                    dwell_ms=int(dwell_duration * 1000.0), is_staff=is_staff, confidence=conf,
                                    session_seq=self.get_session_seq(visitor_id)
                                )
                                track_states[track_id] = (current_zone, enter_time, True)  # Mark as emitted

            frame_idx += 1
            
        cap.release()
        
        # ── Two-pass entry emission for entry cameras ──────────────────────────
        # After processing all frames, emit exactly one ENTRY per unique visitor
        # that appeared for >= MIN_FRAMES (filters out single-frame ghost detections).
        if "entry" in camera_id.lower():
            MIN_FRAMES = 2  # Must appear in at least 2 sampled frames to count (filters single-frame ghosts)
            
            # Build map: visitor_id -> (first_timestamp, frame_count, is_staff, avg_conf)
            visitor_summary: Dict[str, Dict] = {}
            
            for t_id, positions in self.active_tracks.get(camera_id, {}).items():
                if len(positions) < MIN_FRAMES:
                    continue  # Skip ghost/noise tracks
                    
                # Resolve visitor_id for this track
                key = (camera_id, t_id)
                vid = self.tracker_manager.local_to_global.get(key)
                if vid is None:
                    continue
                    
                profile = self.tracker_manager.visitor_profiles.get(vid, {})
                
                # Use LOCAL staff vote ratio instead of global profile (avoids cross-camera contamination).
                # A track is staff if >= 40% of its frames were locally detected as staff uniform.
                local_votes = local_track_staff_votes.get(t_id, 0)
                local_total = local_track_frame_count.get(t_id, 1)
                is_staff_track = (local_votes / local_total) >= 0.40
                first_ts = positions[0][2]
                
                if vid not in visitor_summary:
                    visitor_summary[vid] = {
                        "first_ts": first_ts,
                        "is_staff": is_staff_track,
                        "frame_count": len(positions),
                    }
                else:
                    # Merge: earliest timestamp wins, accumulate frame count
                    if first_ts < visitor_summary[vid]["first_ts"]:
                        visitor_summary[vid]["first_ts"] = first_ts
                    visitor_summary[vid]["frame_count"] += len(positions)
                    if is_staff_track:
                        visitor_summary[vid]["is_staff"] = True
            
            print(f"  Entry camera {camera_id}: {len(visitor_summary)} valid tracks "
                  f"({sum(1 for v in visitor_summary.values() if not v['is_staff'])} customers, "
                  f"{sum(1 for v in visitor_summary.values() if v['is_staff'])} staff)")
            
            for vid, info in visitor_summary.items():
                self.emitter.emit(
                    store_id=self.store_id,
                    camera_id=camera_id,
                    visitor_id=vid,
                    event_type="ENTRY",
                    timestamp=info["first_ts"],
                    is_staff=info["is_staff"],
                    confidence=0.90,
                    session_seq=self.get_session_seq(vid),
                )
        # ───────────────────────────────────────────────────────────────────────

        print(f"Finished processing camera {camera_id}.")

    def _run_simulation(self, camera_id: str, zones: Dict[str, Tuple[int, int, int, int]]):
        """
        Fallback simulation mode to generate events from video structure if YOLO isn't accessible.
        It generates a realistic set of visitor events to allow API ingestion testing.
        """
        print(f"Running pipeline simulation for camera: {camera_id}")
        c_id_lower = camera_id.lower()
        
        # Simulating 5 visitors
        for idx in range(1, 6):
            visitor_id = f"VIS_sim{idx:02d}"
            is_staff = (idx == 5)  # Make visitor 5 a staff member
            
            # Offsets
            entry_offset = idx * 120  # staggered entries
            entry_time = self.base_time + timedelta(seconds=entry_offset)
            
            if "entry" in c_id_lower:
                # ENTRY event
                self.emitter.emit(
                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                    event_type="ENTRY", timestamp=entry_time, is_staff=is_staff,
                    confidence=0.95, session_seq=self.get_session_seq(visitor_id)
                )
                # EXIT event 10 minutes later
                exit_time = entry_time + timedelta(minutes=10)
                self.emitter.emit(
                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                    event_type="EXIT", timestamp=exit_time, is_staff=is_staff,
                    confidence=0.95, session_seq=self.get_session_seq(visitor_id)
                )
                
            elif "zone" in c_id_lower:
                # ZONE ENTER / EXIT / DWELL
                for zone_id in ["SKINCARE", "LIPSTICK"]:
                    z_enter = entry_time + timedelta(minutes=1)
                    self.emitter.emit(
                        store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                        event_type="ZONE_ENTER", timestamp=z_enter, zone_id=zone_id,
                        is_staff=is_staff, confidence=0.92, session_seq=self.get_session_seq(visitor_id)
                    )
                    # ZONE DWELL (45 seconds later)
                    z_dwell = z_enter + timedelta(seconds=45)
                    self.emitter.emit(
                        store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                        event_type="ZONE_DWELL", timestamp=z_dwell, zone_id=zone_id,
                        dwell_ms=45000, is_staff=is_staff, confidence=0.92,
                        session_seq=self.get_session_seq(visitor_id)
                    )
                    # ZONE EXIT
                    z_exit = z_dwell + timedelta(seconds=15)
                    self.emitter.emit(
                        store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                        event_type="ZONE_EXIT", timestamp=z_exit, zone_id=zone_id,
                        dwell_ms=60000, is_staff=is_staff, confidence=0.92,
                        session_seq=self.get_session_seq(visitor_id)
                    )
                    
            elif "billing" in c_id_lower or "cam 5" in c_id_lower:
                # BILLING_QUEUE_JOIN
                b_join = entry_time + timedelta(minutes=6)
                self.emitter.emit(
                    store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                    event_type="BILLING_QUEUE_JOIN", timestamp=b_join,
                    is_staff=is_staff, confidence=0.96, queue_depth=idx,
                    session_seq=self.get_session_seq(visitor_id)
                )
                
                # Mock abandonment for visitor 2
                if idx == 2:
                    b_abandon = b_join + timedelta(minutes=2)
                    self.emitter.emit(
                        store_id=self.store_id, camera_id=camera_id, visitor_id=visitor_id,
                        event_type="BILLING_QUEUE_ABANDON", timestamp=b_abandon,
                        is_staff=is_staff, confidence=0.96, session_seq=self.get_session_seq(visitor_id)
                    )

    def process_store(self):
        """
        Scans the video directory and processes all available CCTV mp4 files.
        """
        if not os.path.exists(self.video_dir):
            print(f"Store video directory not found: {self.video_dir}")
            return
            
        video_files = [f for f in os.listdir(self.video_dir) if f.endswith(".mp4")]
        if not video_files:
            print(f"No MP4 files found in {self.video_dir}")
            return
            
        print(f"Found {len(video_files)} video clips in {self.video_dir}")
        for file in video_files:
            camera_id = file.replace(".mp4", "")
            video_path = os.path.join(self.video_dir, file)
            self.process_video_file(video_path, camera_id)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Process CCTV videos for a store.")
    parser.add_argument("--store_id", default="ST1076", help="Store Identifier")
    parser.add_argument("--video_dir", default=r"d:\purple_hackathon\Store 2", help="Directory containing mp4 videos")
    parser.add_argument("--output", default="events_output.jsonl", help="Output JSONL events path")
    parser.add_argument("--frame_skip", type=int, default=15, help="Frame skipping value (e.g. 15 for 1fps)")
    
    parser.add_argument("--staff_color", default="black", choices=["black", "purple"],
                        help="Staff uniform color: 'black' for Store 1, 'purple' for Store 2")
    
    args = parser.parse_args()
    
    pipeline = StoreIntelligencePipeline(
        store_id=args.store_id,
        video_dir=args.video_dir,
        output_jsonl=args.output,
        frame_skip=args.frame_skip,
        staff_color=args.staff_color
    )
    pipeline.process_store()
