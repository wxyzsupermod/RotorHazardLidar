// Create the main visualization component
const LidarVisualization = () => {
  const [scanData, setScanData] = useState([]);
  const [threshold, setThreshold] = useState(100);
  const [error, setError] = useState(null);
  const canvasRef = useRef(null);

  // Fetch data from the server
  useEffect(() => {
      const fetchData = async () => {
          try {
              const response = await fetch('/lidar/data');
              const data = await response.json();
              
              if (data.error) {
                  setError(data.error);
              } else {
                  setError(null);
                  setScanData(data.scan || []);
                  setThreshold(data.threshold / 10); // Convert mm to cm
              }
          } catch (err) {
              setError('Failed to fetch LIDAR data');
          }
      };
      
      // Poll every 100ms
      const interval = setInterval(fetchData, 100);
      return () => clearInterval(interval);
  }, []);

  // Draw visualization on canvas
  useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      
      const ctx = canvas.getContext('2d');
      const width = canvas.width;
      const height = canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;
      const scale = 2;
      
      // Clear canvas
      ctx.clearRect(0, 0, width, height);
      
      // Your existing canvas drawing code here...
      // (Keep all the drawing logic from your original lidar-viz.js)
      
  }, [scanData, threshold]);

  return (
      <div className="lidar-container">
          <h1>LIDAR Visualization</h1>
          {error && (
              <div style={{ color: 'red', marginBottom: '1rem' }}>
                  {error}
              </div>
          )}
          <canvas 
              ref={canvasRef}
              width={600}
              height={600}
              style={{ width: '100%', height: 'auto' }}
          />
          <div style={{ marginTop: '1rem', fontSize: '0.9rem', color: '#666' }}>
              Threshold: {threshold}cm
          </div>
      </div>
  );
};

// Render the component
ReactDOM.render(
  <LidarVisualization />,
  document.getElementById('root')
);