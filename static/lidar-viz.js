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
  
  // ... rest of your visualization code remains the same ...
};

export default LidarVisualization;