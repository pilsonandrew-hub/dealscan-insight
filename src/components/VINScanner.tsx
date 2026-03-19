import React, { useState, useEffect, useRef } from 'react';
import { Camera, X, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://dealscan-insight-production.up.railway.app';

const VINScanner = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<'manual' | 'camera'>('manual');
  const [vin, setVin] = useState('');
  const [decodedData, setDecodedData] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let barcodeDetector;
    let stream;
    let scanId;

    if (mode === 'camera' && scanning) {
      if ('BarcodeDetector' in window) {
        barcodeDetector = new BarcodeDetector({ formats: ['code_39', 'code_128', 'ean_13'] });
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
          .then((mediaStream) => {
            stream = mediaStream;
            if (videoRef.current) {
              videoRef.current.srcObject = stream;
              videoRef.current.play();
            }

            const detect = () => {
              barcodeDetector.detect(videoRef.current)
                .then((barcodes) => {
                  if (barcodes.length > 0) {
                    const barcode = barcodes[0];
                    setVin(barcode.rawValue);
                    setScanning(false);
                    setIsOpen(false);
                  } else {
                    scanId = requestAnimationFrame(detect);
                  }
                })
                .catch(() => {
                  scanId = requestAnimationFrame(detect);
                });
            };
            detect();
          })
          .catch(() => {
            setError('Camera access denied or not available.');
            setScanning(false);
          });
      } else {
        setError('BarcodeDetector API not supported. Please enter VIN manually.');
        setScanning(false);
      }
    }

    return () => {
      if (scanId) cancelAnimationFrame(scanId);
      if (stream) stream.getTracks().forEach(track => track.stop());
    };
  }, [mode, scanning]);

  const decodeVin = async (vinCode: string) => {
    setError('');
    if (!vin || vin.length < 11) {
      setError('Please enter a valid VIN');
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/vin/decode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vin: vinCode })
      });
      if (!response.ok) throw new Error('Failed to decode VIN');
      const data = await response.json();
      setDecodedData(data);
    } catch (e) {
      setError('Error decoding VIN');
    }
  };

  return (
    <>
      <Button
        className=fixed bottom-20 right-4 z-50 md:bottom-6 md:right-6
        onClick={() => {
          setIsOpen(true);
          setDecodedData(null);
          setVin('');
          setError('');
          setMode('manual');
        }}
        aria-label=Open VIN scanner
      >
        <Camera />
      </Button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>VIN Scanner</DialogTitle>
            <Button variant=ghost onClick={() => setIsOpen(false)} aria-label=Close>
              <X />
            </Button>
          </DialogHeader>

          {decodedData ? (
            <div className=p-4>
              <h3 className=text-xl font-semibold>Vehicle Details</h3>
              <p>Year: {decodedData.year}</p>
              <p>Make: {decodedData.make}</p>
              <p>Model: {decodedData.model}</p>
              <p>Body Type: {decodedData.body_type}</p>
              {/* Optional scoring UI can be added here */}
              <Button onClick={() => {
                setDecodedData(null);
                setVin('');
                setMode('manual');
              }} className=mt-4>
                Scan Another VIN
              </Button>
            </div>
          ) : (
            <div className=space-y-4>
              <div className=flex justify-center space-x-4>
                <Button onClick={() => {
                  setMode('manual');
                  setError('');
                  setScanning(false);
                }} variant={mode === 'manual' ? 'default' : 'outline'}>
                  Manual Entry
                </Button>
                <Button onClick={() => {
                  setMode('camera');
                  setError('');
                  setScanning(true);
                }} variant={mode === 'camera' ? 'default' : 'outline'}>
                  Camera Scan
                </Button>
              </div>

              {mode === 'manual' ? (
                <>
                  <Input
                    placeholder=Enter VIN
                    value={vin}
                    onChange={(e) => setVin(e.target.value.toUpperCase())}
                    className=uppercase
                  />
                  <Button onClick={() => decodeVin(vin)} disabled={!vin}>
                    Decode VIN
                    <Search className=ml-2 />
                  </Button>
                </>
              ) : (
                <div className=flex flex-col items-center>
                  {error && <p className=text-red-500>{error}</p>}
                  <video ref={videoRef} className=w-full max-w-sm rounded />
                  {!scanning && !error && <Button onClick={() => setScanning(true)}>Start Scan</Button>}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default VINScanner;

