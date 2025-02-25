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
        self.detection_window = 0.5  # Time window in seconds to match detections
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


        # Register all options
        self.rhapi.fields.register_option(port_field, 'lidar_control')
        self.rhapi.fields.register_option(baud_field, 'lidar_control')
        self.rhapi.fields.register_option(timeout_field, 'lidar_control')
        self.rhapi.fields.register_option(distance_field, 'lidar_control')

        
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
        """Start the LIDAR scanning process."""
        if self.is_running:
            return
            
        try:
            port = self.rhapi.db.option('lidar_port')
            baudrate = int(self.rhapi.db.option('lidar_baudrate'))
            timeout = int(self.rhapi.db.option('lidar_timeout'))
            self.detection_threshold = int(self.rhapi.db.option('detection_distance'))
            
            self.lidar = RPLidar(port, baudrate=baudrate, timeout=timeout)
            self.is_running = True
            
            # Start scanning in a separate greenlet
            self.scanning_greenlet = gevent.spawn(self.scan_loop)
            
            self.rhapi.ui.message_notify('LIDAR scanning started')
        except Exception as e:
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
        """Main LIDAR scanning loop."""
        try:
            while self.is_running:
                for scan in self.lidar.iter_scans():
                    if not self.is_running:
                        break
                        
                    # Convert scan data to simplified format for visualization
                    with self.scan_lock:  # Protect data access with lock
                        scan_data = []
                        for _, angle, distance in scan:
                            # Convert to cartesian coordinates for easier visualization
                            # Scale distance down to fit visualization (divide by 10 to convert mm to cm)
                            distance = distance / 10
                            x = distance * math.cos(math.radians(angle))
                            y = distance * math.sin(math.radians(angle))
                            scan_data.append({
                                'angle': angle,
                                'distance': distance,
                                'x': x,
                                'y': y
                            })
                            
                            # Check for detections in the gate area
                            if (angle < 10 or angle > 350) and distance * 10 < self.detection_threshold:
                                self.rhapi.ui.message_notify('Lidar detected a thing')
                                self.last_detection_time = self.rhapi.server.monotonic_to_epoch_millis(
                                    gevent.time.monotonic()
                                )
                        
                        self.last_scan_data = scan_data
                    
                    gevent.idle()  # Allow other operations to proceed
                    
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
    
    def on_lap_recorded(self, args):
        """Handler for lap recording events."""
        if not self.is_running or not self.last_detection_time:
            return

        lap_time = args.get('lap').lap_time_stamp if args.get('lap') else 0

        # Compare timestamps
        time_diff = abs(lap_time - self.last_detection_time) / 1000.0  # Convert to seconds

        if time_diff > self.detection_window:
            # Invalid lap - no LIDAR detection within window
            self.rhapi.ui.message_notify(
                f'Warning: Lap recorded without LIDAR validation (diff: {time_diff:.2f}s)'
            )

            # Get the pilot_id and lap_number from the args
            pilot_id = args.get('pilot_id')
            lap_number = args.get('lap').lap_number if args.get('lap') else None
            args.get('lap').invalid = True
            args.get('lap').deleted = True
            
    
    def on_race_stop(self, args):
        """Handler for race stop events."""
        # Clear the last detection time when race stops
        self.stop_lidar()
    
    def on_race_start(self, args):
        """Handler for race start events."""
        self.rhapi.ui.message_notify("Starting Lidar")
        self.stop_lidar()
        self.start_lidar()

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