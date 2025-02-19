import React, { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';

const LidarVisualization = () => {
  const [scanData, setScanData] = useState([]);
  const [threshold, setThreshold] = useState(100);
  const [error, setError] = useState(null);
  const canvasRef = useRef(null);
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/lidar/data');
        const data = await response.json();
        
        if (data.error) {
          setError(data.error);
        } else {
            setError(null);
          }
        
        setScanData(data.scan || []);
        setThreshold(data.threshold / 10); // Convert mm to cm
      } catch (err) {
        setError('Failed to fetch LIDAR data');
      }
    };
    
    // Poll every 100ms
    const interval = setInterval(fetchData, 100);
    return () => clearInterval(interval);
  }, []);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const scale = 2; // Scale factor to make visualization larger/smaller
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw coordinate grid
    ctx.strokeStyle = '#2c3e50';
    ctx.lineWidth = 0.5;
    
    // Draw concentric circles
    for (let r = 50; r <= 300; r += 50) {
      ctx.beginPath();
      ctx.arc(centerX, centerY, r * scale, 0, 2 * Math.PI);
      ctx.stroke();
      
      // Add distance labels
      ctx.fillStyle = '#2c3e50';
      ctx.font = '12px Arial';
      ctx.fillText(`${r}cm`, centerX + r * scale, centerY);
    }
    
    // Draw threshold circle
    ctx.strokeStyle = '#e74c3c';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, threshold * scale, 0, 2 * Math.PI);
    ctx.stroke();
    
    // Draw scan points
    ctx.fillStyle = '#3498db';
    scanData.forEach(point => {
      const x = centerX + point.x * scale;
      const y = centerY + point.y * scale;
      
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, 2 * Math.PI);
      ctx.fill();
    });
    
    // Draw detection zone
    ctx.fillStyle = 'rgba(46, 204, 113, 0.2)';
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, threshold * scale, -Math.PI/18, Math.PI/18);
    ctx.lineTo(centerX, centerY);
    ctx.fill();
    
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, threshold * scale, Math.PI - Math.PI/18, Math.PI + Math.PI/18);
    ctx.lineTo(centerX, centerY);
    ctx.fill();
    
  }, [scanData, threshold]);
  
  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle>LIDAR View</CardTitle>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="relative w-full aspect-square">
          <canvas 
            ref={canvasRef}
            width={600}
            height={600}
            className="w-full h-full border rounded-lg bg-black/5"
          />
          <div className="absolute top-2 right-2 text-sm text-gray-600">
            Each circle = 50cm
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default LidarVisualization;