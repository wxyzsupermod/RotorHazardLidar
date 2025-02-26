import json
from datetime import datetime
import math
from rplidar import RPLidar
from eventmanager import Evt
from RHUI import UIField, UIFieldType
from Database import ProgramMethod
import gevent
import asyncio
import threading
from gevent import monkey; monkey.patch_all()

class LidarValidator:
    def __init__(self, rhapi):
        self.rhapi = rhapi
        self.lidar = None
        self.detection_threshold = None
        self.last_detection_time = None
        self.detection_window = 1.0  # Time window in seconds to match detections
        self.is_running = False
        self.scanning_greenlet = None
        self.last_scan_data = []  # Initialize empty list for scan data
        self.scan_lock = threading.Lock()  # Add a lock for thread-safe data access
        
        # Register port option
        port_field = UIField('lidar_port', 'LIDAR Port', UIFieldType.TEXT, 
                   value='/dev/ttyUSB0',
                   desc='Serial port for RPLidar C1')
        baud_field = UIField('lidar_baudrate', 'Baud Rate', UIFieldType.BASIC_INT,
                   value='460800',
                   desc='Serial baud rate for RPLidar C1')
        timeout_field = UIField('lidar_timeout', 'Timeout (seconds)', UIFieldType.BASIC_INT,
                   value='10',
                   desc='Connection timeout in seconds')
        distance_field = UIField('detection_distance', 'Detection Distance (mm)', UIFieldType.BASIC_INT,
                   value='1000',
                    desc='Distance threshold for detection in millimeters')
        window_field = UIField('detection_window', 'Detection Window (seconds)', UIFieldType.TEXT,
                value='1.0',
                desc='Time window for matching LIDAR detection with lap crossing')

        # Register all options
        self.rhapi.fields.register_option(port_field, 'lidar_control')
        self.rhapi.fields.register_option(baud_field, 'lidar_control')
        self.rhapi.fields.register_option(timeout_field, 'lidar_control')
        self.rhapi.fields.register_option(distance_field, 'lidar_control')
        self.rhapi.fields.register_option(window_field, 'lidar_control')

        
        # Create UI panel
        self.rhapi.ui.register_panel('lidar_control', 'LIDAR Control', 'settings')
        
        # Add control buttons
        self.rhapi.ui.register_quickbutton('lidar_control', 'start_lidar', 
                                         'Start LIDAR', self.start_lidar)
        self.rhapi.ui.register_quickbutton('lidar_control', 'stop_lidar',
                                         'Stop LIDAR', self.stop_lidar)
        self.rhapi.ui.register_quickbutton('lidar_control', 'calibrate_lidar',
                                         'Calibrate', self.calibrate)
        self.rhapi.ui.register_quickbutton('lidar_control', 'view_lidar',
                                         'View LIDAR', self.open_visualization)
        
        # Register event handlers
        self.rhapi.events.on(Evt.RACE_LAP_RECORDED, self.on_lap_recorded)
        self.rhapi.events.on(Evt.RACE_STOP, self.on_race_stop)
        self.rhapi.events.on(Evt.RACE_START, self.on_race_start)
        self.rhapi.events.on(Evt.LAPS_SAVE, self.on_race_stop)
        self.rhapi.events.on(Evt.LAPS_DISCARD, self.on_race_stop)        

        # Register the visualization page and API endpoint
        from flask import Blueprint, jsonify, render_template
        import os

        # Get the directory where this plugin file is located
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create blueprint with absolute paths
        bp = Blueprint(
            'lidar_viz',
            __name__,
            template_folder=os.path.join(plugin_dir, 'templates'),
            static_folder=os.path.join(plugin_dir, 'static'),
            static_url_path='/static/lidar-viz' 
        )
        
        @bp.route('/lidar')
        def lidar_view():
            """Serve the LIDAR visualization page."""
            try:
                self.rhapi.ui.message_notify('Lidar view endpoint accessed')
                return render_template('lidar_viz.html')
            except Exception as e:
                self.rhapi.ui.message_alert(f'Error loading template: {str(e)}')
                return f'Error: {str(e)}'
            
       
        @bp.route('/lidar/data')
        def lidar_data():
            """Serve LIDAR scan data as JSON."""
            if not self.is_running:
                return jsonify({
                    'error': 'LIDAR not running',
                    'scan': [],
                    'threshold': self.detection_threshold or 1000
                })
            
            with self.scan_lock:  # Protect data access with lock
                return jsonify({
                    'scan': self.last_scan_data,
                    'threshold': self.detection_threshold
                })
                
        # Register the blueprint
        self.rhapi.ui.blueprint_add(bp)

            
    def start_lidar(self, args=None):
        """Start the LIDAR scanning process with improved error handling."""
        if self.is_running:
            self.rhapi.ui.message_notify('LIDAR already running')
            return
            
        try:
            # Get configuration from database
            port = self.rhapi.db.option('lidar_port')
            baudrate = int(self.rhapi.db.option('lidar_baudrate'))
            timeout = int(self.rhapi.db.option('lidar_timeout'))
            self.detection_threshold = int(self.rhapi.db.option('detection_distance'))
            
            # Get detection window from options (or use default if not found)
            try:
                window_str = self.rhapi.db.option('detection_window')
                self.detection_window = float(window_str)
            except (ValueError, TypeError):
                # Fall back to default if conversion fails
                self.detection_window = 1.0
                
            # Initialize LIDAR with error handling
            self.rhapi.ui.message_notify(f'LIDAR connecting to {port} at {baudrate} baud...')
            
            try:
                # Check if port exists before connecting
                import os
                if not os.path.exists(port):
                    self.rhapi.ui.message_alert(f'LIDAR port {port} does not exist')
                    return
                    
                # Connect to LIDAR with explicit timeout
                self.lidar = RPLidar(port, baudrate=baudrate, timeout=timeout)
                
                # Test LIDAR with info request
                info = self.lidar.get_info()
                self.rhapi.ui.message_notify(f'LIDAR connected successfully: {info}')
                
            except Exception as lidar_err:
                self.rhapi.ui.message_alert(f'LIDAR hardware error: {str(lidar_err)}')
                if self.lidar:
                    try:
                        self.lidar.disconnect()
                    except:
                        pass
                self.lidar = None
                return
                
            # Mark as running before starting greenlet
            self.is_running = True
            
            # Start scanning in a separate greenlet
            self.rhapi.ui.message_notify('LIDAR starting scan loop...')
            self.scanning_greenlet = gevent.spawn(self.scan_loop)
            
            self.rhapi.ui.message_notify(f'LIDAR scanning started (detection window: {self.detection_window}s)')
            
        except Exception as e:
            self.is_running = False
            if self.lidar:
                try:
                    self.lidar.disconnect()
                except:
                    pass
                self.lidar = None
                
            self.rhapi.ui.message_alert(f'Failed to start LIDAR: {str(e)}')            
    def stop_lidar(self, args=None):
        """Stop the LIDAR scanning process."""
        self.is_running = False
        if self.scanning_greenlet:
            self.scanning_greenlet.kill()
            self.scanning_greenlet = None
            
        if self.lidar:
            self.lidar.stop()
            self.lidar.disconnect()
            self.lidar = None
            
        self.rhapi.ui.message_notify('LIDAR scanning stopped')
        
    def scan_loop(self):
        """
        Main LIDAR scanning loop with improved fast-object detection.
        """
        try:
            # Initialize a detection buffer to help catch fast-moving objects
            detection_buffer = []
            max_buffer_size = 3  # Number of scans to consider for detection
            detection_angle_range = 90  # Increased from 10 to 20 degrees
            
            # Set scanner to motor speed to maximum if available
            if hasattr(self.lidar, 'set_motor_pwm'):
                self.lidar.set_motor_pwm(1000)  # Maximum motor speed (if supported)
            
            while self.is_running:
                for scan in self.lidar.iter_scans(max_buf_meas=10000):  # Increased buffer for faster processing
                    if not self.is_running:
                        break
                        
                    # Process scan quickly before acquiring lock
                    has_detection = False
                    gate_detections = []
                    
                    # Convert scan data to simplified format for visualization and detection
                    scan_data = []
                    for _, angle, distance in scan:
                        # Scale distance down to fit visualization (divide by 10 to convert mm to cm)
                        distance_cm = distance / 10
                        
                        # Check for detections in the gate area (with wider angle range)
                        if ((angle < detection_angle_range) or (angle > (360 - detection_angle_range))) and distance < self.detection_threshold:
                            gate_detections.append({
                                'angle': angle,
                                'distance': distance
                            })
                            has_detection = True
                        
                        # Add to visualization data
                        x = distance_cm * math.cos(math.radians(angle))
                        y = distance_cm * math.sin(math.radians(angle))
                        scan_data.append({
                            'angle': angle,
                            'distance': distance_cm,
                            'x': x,
                            'y': y
                        })
                    
                    # Update detection buffer - add current scan result
                    detection_buffer.append(has_detection)
                    if len(detection_buffer) > max_buffer_size:
                        detection_buffer.pop(0)  # Remove oldest detection
                    
                    # Consider detection valid if any recent scans had a detection
                    if any(detection_buffer):
                        self.last_detection_time = self.rhapi.server.monotonic_to_epoch_millis(
                            gevent.time.monotonic()
                        )
                    
                    # Update visualization data with thread safety
                    with self.scan_lock:
                        self.last_scan_data = scan_data
                    
                    # Minimal sleep to allow other operations to proceed without slowing scan rate
                                        
        except Exception as e:
            self.rhapi.ui.message_alert(f'LIDAR scanning error: {str(e)}')
            self.stop_lidar()

    def open_visualization(self, args=None):
        """Open the LIDAR visualization."""
        try:
            # Return JavaScript that will be executed on the client side
            return {'script': 'window.open("/lidar", "_blank")'}
        except Exception as e:
            self.rhapi.ui.message_alert(f'Failed to open visualization: {str(e)}')
            return False
    
    def invalidate_lap(self, lap, args, reason="unspecified"):
        """
        Invalidate a lap with proper logging and error handling.
        
        Args:
            lap: The lap object to invalidate
            args: The event arguments containing additional lap data
            reason: The reason for invalidation for logging purposes
        """
        if not lap:
            return
            
        try:
            # Mark the lap as invalid and deleted
            lap.deleted = True
                        
            # Try to get additional info for logging
            pilot_id = args.get('pilot_id')
            pilot_name = args.get('pilot_name', 'Unknown pilot')
            lap_number = getattr(lap, 'lap_number', 'Unknown')
            
            self.rhapi.ui.message_notify(
                f'Invalidated lap for {pilot_name} (lap {lap_number}) - {reason}'
            )
        except Exception as e:
            self.rhapi.ui.message_notify(f'Error invalidating lap: {str(e)}')

    def on_lap_recorded(self, args):
        """Handler for lap recording events with direct timestamp comparison."""
        # Skip validation if LIDAR is not running
        if not self.is_running:
            self.rhapi.ui.message_notify("LIDAR not running - lap validation skipped")
            return

        # Get the lap data
        lap = args.get('lap')
        if not lap:
            return
        
        # Get the current time for reference
        current_time = self.rhapi.server.monotonic_to_epoch_millis(gevent.time.monotonic())
        
        # Skip validation if we don't have a recent LIDAR detection
        if not self.last_detection_time:
            self.rhapi.ui.message_notify("No LIDAR detections - lap validation skipped")
            # Also invalidate the lap since there was no LIDAR detection at all
            self.invalidate_lap(lap, args, "No LIDAR detection available")
            return
        
        # Log raw values for debugging
        self.rhapi.ui.message_notify(f"DEBUG: Current epoch ms time: {current_time}")
        self.rhapi.ui.message_notify(f"DEBUG: LIDAR detection timestamp: {self.last_detection_time}")
        
        # Calculate the time difference between now and the last LIDAR detection
        time_diff = abs(current_time - self.last_detection_time) / 1000.0  # Convert ms to seconds
        
        # Log the time difference for debugging
        self.rhapi.ui.message_notify(f'LIDAR validation: time diff = {time_diff:.2f}s (threshold: {self.detection_window:.2f}s)')
        
        # Check if the time difference is within our validation window
        if time_diff > self.detection_window:
            # Invalid lap - no LIDAR detection within window
            self.rhapi.ui.message_notify(
                f'Warning: Invalid lap detected! No LIDAR detection within {self.detection_window}s window'
            )
            
            # Use the shared invalidation function
            self.invalidate_lap(lap, args, f"No LIDAR detection within {self.detection_window}s window")
        else:
            # Valid lap - LIDAR detection confirms it
            self.rhapi.ui.message_notify('Lap validated by LIDAR detection ✓')
            
    
    def on_race_stop(self, args):
        """Handler for race stop events."""
        self.rhapi.ui.message_notify("LIDAR: Race stopped, shutting down LIDAR")
        try:
            # Set a flag first to avoid race condition
            self.is_running = False
            
            # Give time for scanning loop to notice the flag change
            gevent.sleep(0.2)
            
            # Then clean up resources
            if self.scanning_greenlet:
                try:
                    self.scanning_greenlet.kill(timeout=2.0)
                except Exception as e:
                    self.rhapi.ui.message_notify(f"LIDAR: Error stopping scan greenlet: {str(e)}")
                self.scanning_greenlet = None
                
            if self.lidar:
                try:
                    self.lidar.stop()
                    self.lidar.disconnect()
                except Exception as e:
                    self.rhapi.ui.message_notify(f"LIDAR: Error disconnecting: {str(e)}")
                self.lidar = None
                
            self.rhapi.ui.message_notify('LIDAR scanning stopped successfully')
            
        except Exception as e:
            self.rhapi.ui.message_alert(f'LIDAR stop error: {str(e)}')

    def on_race_start(self, args):
        """Handler for race start events."""
        self.rhapi.ui.message_notify("LIDAR: Starting for new race")
        
        # Make sure LIDAR is cleanly stopped before starting
        try:
            # First ensure we are stopped
            self.on_race_stop(args)
            
            # Small delay to ensure resources are freed
            gevent.sleep(0.5)
            
            # Now start fresh
            if not self.is_running:
                self.start_lidar()
                
                # Make sure the LIDAR actually started
                if not self.is_running:
                    raise Exception("LIDAR failed to start properly")
                    
                # Small delay to ensure LIDAR is running before race proceeds
                gevent.sleep(0.2)
                
                self.rhapi.ui.message_notify("LIDAR ready for race")
            else:
                self.rhapi.ui.message_notify("LIDAR was already running")
        
        except Exception as e:
            self.rhapi.ui.message_alert(f'LIDAR start error: {str(e)}')
            
    def calibrate(self, args=None):
        """
        Calibrate the LIDAR by taking a 10-second average of distances in the gate area.
        This sets the detection threshold based on actual measurements.
        """
        self.rhapi.ui.message_notify('Starting LIDAR calibration (10 seconds)...')
        
        # Make sure LIDAR is running
        was_already_running = self.is_running
        if not self.is_running:
            self.start_lidar()
            
        # If we couldn't start the LIDAR, abort calibration
        if not self.is_running:
            self.rhapi.ui.message_alert('Calibration failed: Could not start LIDAR')
            return
        
        # Create data collection variables
        gate_distances = []
        start_time = gevent.time.monotonic()
        calibration_duration = 10  # 10 seconds of data collection
        
        try:
            # Collect data for 10 seconds
            while gevent.time.monotonic() - start_time < calibration_duration:
                # Short sleep to prevent CPU overloading
                gevent.sleep(0.1)
                
                # Get latest scan data with lock protection
                with self.scan_lock:
                    # Only collect data in the "gate area" (angles near 0/360 degrees)
                    for point in self.last_scan_data:
                        angle = point['angle']
                        # Consider points within the gate area (adjust range as needed)
                        if angle < 10 or angle > 350:
                            # Convert back to mm for threshold (data is stored in cm)
                            gate_distances.append(point['distance'] * 10)
            
            # Calculate the average if we have data
            if gate_distances:
                # Calculate average and add a margin (e.g., 80% of the average)
                avg_distance = sum(gate_distances) / len(gate_distances)
                # Set threshold to 80% of the average distance
                calibrated_threshold = int(avg_distance * 0.8)
                
                 
                # Update the detection threshold
                self.detection_threshold = calibrated_threshold
                
                # Update the option value in the database
                self.rhapi.db.option_set('detection_distance', str(calibrated_threshold))
                
                            
                # Notify user of successful calibration
                self.rhapi.ui.message_notify(
                    f'Calibration complete: Detection threshold set to {calibrated_threshold}mm '
                    f'(based on average of {len(gate_distances)} readings)'
                )
            else:
                self.rhapi.ui.message_alert('Calibration failed: No data collected in gate area')
        
        except Exception as e:
            self.rhapi.ui.message_alert(f'Calibration error: {str(e)}')
        
        finally:
            # Stop LIDAR if it wasn't running before
            if not was_already_running:
                self.stop_lidar()

def initialize(rhapi):
    """Initialize the plugin."""
    return LidarValidator(rhapi)