import json
from datetime import datetime
import math
from rplidar import RPLidar
from eventmanager import Evt
from RHUI import UIField, UIFieldType
from Database import ProgramMethod
import gevent

class LidarValidator:
    def __init__(self, rhapi):
        self.rhapi = rhapi
        
        # Register the visualization page
        from flask import Blueprint
        
        bp = Blueprint(
            'lidar_viz',
            __name__
        )
        
        @bp.route('/lidar')
        def lidar_view():
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>LIDAR Visualization</title>
            </head>
            <body>
                <div id="root"></div>
                <script>
                    window.socket = new WebSocket(`ws://${window.location.host}/socket`);
                </script>
            </body>
            </html>
            '''
            
        # Register the blueprint
        self.rhapi.ui.blueprint_add(bp)
        self.lidar = None
        self.detection_threshold = None
        self.last_detection_time = None
        self.detection_window = 0.5  # Time window in seconds to match detections
        self.is_running = False
        self.scanning_greenlet = None
        
        # Register our options and add them to the panel
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
        
        # Add visualization button
        self.rhapi.ui.register_quickbutton('lidar_control', 'view_lidar',
                                         'View LIDAR', self.open_visualization)
        
        # Register event handlers
        self.rhapi.events.on(Evt.RACE_LAP_RECORDED, self.on_lap_recorded)
        self.rhapi.events.on(Evt.RACE_STOP, self.on_race_stop)
        
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
        if not self.is_running:
            return
            
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
            for scan in self.lidar.iter_scans():
                if not self.is_running:
                    break
                    
                # Check each measurement in the scan
                for _, angle, distance in scan:
                    # We only care about objects directly in front (angle near 0 or 360)
                    if (angle < 10 or angle > 350) and distance < self.detection_threshold:
                        self.last_detection_time = self.rhapi.server.monotonic_to_epoch_millis(
                            gevent.time.monotonic()
                        )
                        
                gevent.idle()  # Allow other operations to proceed
                
        except Exception as e:
            self.rhapi.ui.message_alert(f'LIDAR scanning error: {str(e)}')
            self.stop_lidar()
            
    def on_lap_recorded(self, args):
        """Handler for lap recording events."""
        if not self.is_running or not self.last_detection_time:
            return
            
        lap_time = args.get('lap_timestamp', 0)
        
        # Compare timestamps
        time_diff = abs(lap_time - self.last_detection_time) / 1000.0  # Convert to seconds
        
        if time_diff > self.detection_window:
            # Invalid lap - no LIDAR detection within window
            self.rhapi.ui.message_notify(
                f'Warning: Lap recorded without LIDAR validation (diff: {time_diff:.2f}s)'
            )
            
            # Mark the lap as deleted
            if 'lap_id' in args:
                # Find the lap in the database and mark it as deleted
                race_id = self.rhapi.race.race_id
                if race_id:
                    laps = self.rhapi.db.laps_by_race(race_id)
                    for lap in laps:
                        if lap.id == args['lap_id']:
                            lap.deleted = True
                            break
    
    def on_race_stop(self, args):
        """Handler for race stop events."""
        # Clear the last detection time when race stops
        self.last_detection_time = None
        
    def open_visualization(self, args=None):
        """Open the LIDAR visualization in a new window."""
        self.rhapi.ui.message_notify('Opening LIDAR visualization...')
        # Send javascript command to open new window
        self.rhapi.ui.socket_broadcast('open_lidar_viz', {
            'url': '/lidar'
        })

    def calibrate(self, args=None):
        """Run a calibration sequence."""
        if not self.is_running:
            self.rhapi.ui.message_alert('Start LIDAR before calibrating')
            return
            
        self.rhapi.ui.message_notify('Move drone through gate for calibration...')
        
        # Collect measurements for 5 seconds
        distances = []
        start_time = gevent.time.monotonic()
        
        while gevent.time.monotonic() - start_time < 5:
            for scan in self.lidar.iter_scans():
                for _, angle, distance in scan:
                    if angle < 10 or angle > 350:
                        distances.append(distance)
                        
            gevent.idle()
            
        if distances:
            # Set threshold to minimum distance + 20%
            min_distance = min(distances)
            self.detection_threshold = int(min_distance * 1.2)
            
            # Save to options
            self.rhapi.db.option_set('detection_distance', str(self.detection_threshold))
            
            self.rhapi.ui.message_notify(
                f'Calibration complete. Detection threshold: {self.detection_threshold}mm'
            )
        else:
            self.rhapi.ui.message_alert('Calibration failed - no measurements received')

def initialize(rhapi):
    """Initialize the plugin."""
    return LidarValidator(rhapi)