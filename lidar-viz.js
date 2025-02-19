import React, { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

const LidarVisualization = () => {
  const [scanData, setScanData] = useState([]);
  const [threshold, setThreshold] = useState(100);
  const canvasRef = useRef(null);
  
  useEffect(() => {
    // Use existing socket if in visualization window, or create new if in main UI
    const socket = window.socket || new WebSocket(`ws://${window.location.host}/socket`);
    
    const messageHandler = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'custom_message' && data.content.type === 'open_lidar_viz') {
        // Only handle in main window
        if (!window.socket) {
          window.open(data.content.content.url, 'lidar_visualization', 'width=800,height=800');
        }
      }
      else if (data.type === 'lidar_scan') {
        setScanData(data.scan || []);
        setThreshold(data.threshold || 100);
      }
    };

    socket.addEventListener('message', messageHandler);
    
    // Don't close the socket if it's the shared window.socket
    return () => {
      socket.removeEventListener('message', messageHandler);
      if (!window.socket) {
        socket.close();
      }
    };
  }, []);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !scanData.length) return;
    
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
        <div className="relative w-full aspect-square">
          <canvas 
            ref={canvasRef}
            width={600}
            height={600}
            className="w-full h-full border rounded-lg bg-black/5"
          />
          {/* Distance markers */}
          <div className="absolute top-2 right-2 text-sm text-gray-600">
            Each circle = 50cm
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default LidarVisualization;