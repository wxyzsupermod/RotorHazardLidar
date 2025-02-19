// Simple test component
const TestComponent = () => {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
      const fetchData = async () => {
          try {
              const response = await fetch('/lidar/data');
              const jsonData = await response.json();
              setData(jsonData);
              setError(null);
          } catch (err) {
              setError('Failed to fetch LIDAR data: ' + err.message);
          }
      };

      fetchData();
      const interval = setInterval(fetchData, 1000);
      return () => clearInterval(interval);
  }, []);

  if (error) {
      return (
          <div className="lidar-container" style={{ color: 'red' }}>
              <h2>Error</h2>
              <p>{error}</p>
          </div>
      );
  }

  return (
      <div className="lidar-container">
          <h2>LIDAR Data</h2>
          {data ? (
              <pre style={{ overflow: 'auto', maxHeight: '400px' }}>
                  {JSON.stringify(data, null, 2)}
              </pre>
          ) : (
              <p>Loading data...</p>
          )}
      </div>
  );
};

// Initialize React
try {
  console.log('Initializing React component...');
  const rootElement = document.getElementById('root');
  if (!rootElement) {
      throw new Error('Root element not found!');
  }
  ReactDOM.render(<TestComponent />, rootElement);
  console.log('React component initialized');
} catch (err) {
  console.error('Failed to initialize React:', err);
  document.getElementById('root').innerHTML = 
      `<div style="color: red;">
          Failed to initialize visualization: ${err.message}<br>
          Check browser console for details.
      </div>`;
}