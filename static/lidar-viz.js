import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const LidarVisualization = () => {
  const [scanData, setScanData] = useState([]);
  const [threshold, setThreshold] = useState(1000);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/lidar/data');
        const data = await response.json();
        
        if (data.error) {
          setError(data.error);
        } else {
          setScanData(data.scan);
          setThreshold(data.threshold);
        }
      } catch (err) {
        setError('Failed to fetch LIDAR data: ' + err.message);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 100); // Update every 100ms
    return () => clearInterval(interval);
  }, []);

  const canvasRef = React.useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const scale = 2; // Scale factor to make visualization larger

    // Clear canvas
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, width, height);

    // Draw radar circles
    ctx.strokeStyle = '#dee2e6';
    [50, 100, 150, 200].forEach(radius => {
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius * scale, 0, 2 * Math.PI);
      ctx.stroke();
    });

    // Draw gate area
    ctx.strokeStyle = '#ffc107';
    ctx.beginPath();
    ctx.arc(centerX, centerY, threshold / 10 * scale, -Math.PI/18, Math.PI/18);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(centerX, centerY, threshold / 10 * scale, Math.PI - Math.PI/18, Math.PI + Math.PI/18);
    ctx.stroke();

    // Draw scan points
    scanData.forEach(point => {
      const isInGateArea = (point.angle < 10 || point.angle > 350) && point.distance * 10 < threshold;
      
      ctx.fillStyle = isInGateArea ? '#dc3545' : '#0d6efd';
      ctx.beginPath();
      ctx.arc(
        centerX + point.x * scale,
        centerY - point.y * scale,
        2,
        0,
        2 * Math.PI
      );
      ctx.fill();
    });

    // Draw legend
    ctx.font = '12px Arial';
    ctx.fillStyle = '#495057';
    ctx.fillText('Distance (cm):', 10, 20);
    [50, 100, 150, 200].forEach((radius, index) => {
      ctx.fillText(radius * 10, 10, 40 + index * 20);
    });

  }, [scanData, threshold]);

  return (
    <Card className="w-full max-w-4xl mx-auto">
      <CardHeader>
        <CardTitle>LIDAR Visualization</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="text-red-500">{error}</div>
        ) : (
          <div className="relative">
            <canvas 
              ref={canvasRef} 
              width={800} 
              height={800} 
              className="w-full h-full border rounded-lg"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default LidarVisualization;