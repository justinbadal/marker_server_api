"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Label } from "@/components/ui/label";
import { Terminal, Upload, Play, Settings, CheckCircle2, AlertCircle } from "lucide-react";

export default function Home() {
  const [apiUrl, setApiUrl] = useState("http://localhost:8335");
  const [apiKey, setApiKey] = useState("my-secret-token");
  const [file, setFile] = useState<File | null>(null);
  
  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "completed" | "error">("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [markdown, setMarkdown] = useState<string>("");

  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs
  useEffect(() => {
    if (scrollRef.current) {
        // Find the scrollable viewport inside Shadcn ScrollArea and scroll it to bottom
        const viewport = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
        if (viewport) {
            viewport.scrollTop = viewport.scrollHeight;
        }
    }
  }, [logs]);

  // Polling logic
  useEffect(() => {
    let interval: NodeJS.Timeout;

    if (status === "processing" && jobId) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${apiUrl}/status/${jobId}`, {
            headers: { Authorization: `Bearer ${apiKey}` },
          });
          if (!res.ok) throw new Error("Failed to fetch status");
          const data = await res.json();
          
          if (data.logs && data.logs.length > 0) {
              setLogs(data.logs);
          }

          if (data.status === "completed") {
            setStatus("completed");
            // Fetch markdown content secretly to display
            const mdRes = await fetch(`${apiUrl}/download/${jobId}`, {
               headers: { Authorization: `Bearer ${apiKey}` },
            });
            const text = await mdRes.text();
            setMarkdown(text);
          } else if (data.status === "failed") {
            setStatus("error");
            setErrorMsg(data.error || "Backend job failed");
          }
        } catch (err: any) {
          console.error(err);
        }
      }, 2000);
    }

    return () => clearInterval(interval);
  }, [status, jobId, apiUrl, apiKey]);

  const handleStart = async () => {
    if (!file) return;
    setStatus("uploading");
    setLogs([]);
    setMarkdown("");
    setErrorMsg("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${apiUrl}/convert/async`, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "API Error");

      setJobId(data.job_id);
      setStatus("processing");
      setLogs([`> Job started: ${data.job_id}`]);
    } catch (err: any) {
      setErrorMsg(err.message);
      setStatus("error");
    }
  };

  const handleDownload = () => {
     if (!jobId) return;
     // To download authenticated, we must fetch as blob and create object URL
     fetch(`${apiUrl}/download/${jobId}`, {
        headers: { Authorization: `Bearer ${apiKey}` }
     })
     .then(res => res.blob())
     .then(blob => {
         const url = window.URL.createObjectURL(blob);
         const a = document.createElement('a');
         a.href = url;
         a.download = `${file?.name.replace('.pdf', '') || 'converted'}.md`;
         document.body.appendChild(a);
         a.click();
         a.remove();
     });
  };

  return (
    <main className="container mx-auto p-8 max-w-5xl space-y-6">
      
      <div className="flex items-center gap-3 pb-4 border-b border-border text-zinc-100">
         <Terminal className="w-8 h-8" />
         <h1 className="text-3xl font-bold tracking-tight">MARKER-PDF STUDIO</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Settings & Controls Sidebar */}
        <div className="space-y-6">
          <Card className="bg-zinc-950 border-zinc-800">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-zinc-100"><Settings className="w-4 h-4"/> Connection</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="api-url" className="text-zinc-400">API Endpoint</Label>
                <Input 
                  id="api-url" 
                  value={apiUrl} 
                  onChange={(e) => setApiUrl(e.target.value)} 
                  className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-sm"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="api-key" className="text-zinc-400">Bearer Token</Label>
                <Input 
                  id="api-key" 
                  type="password" 
                  value={apiKey} 
                  onChange={(e) => setApiKey(e.target.value)}
                  className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-sm"
                />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-zinc-950 border-zinc-800">
             <CardHeader>
                <CardTitle className="flex items-center gap-2 text-zinc-100"><Upload className="w-4 h-4"/> Payload</CardTitle>
             </CardHeader>
             <CardContent className="space-y-4">
                <Input 
                  type="file" 
                  accept=".pdf" 
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="bg-zinc-900 border-zinc-800 text-zinc-300 cursor-pointer"
                />
                <Button 
                    onClick={handleStart} 
                    disabled={!file || status === "uploading" || status === "processing"}
                    className="w-full bg-zinc-100 text-zinc-950 hover:bg-zinc-300 font-bold"
                >
                    {status === "uploading" ? "Uploading..." : status === "processing" ? "Converting..." : <><Play className="w-4 h-4 mr-2"/> Start Conversion</>}
                </Button>
                
                {status === "error" && (
                    <div className="p-3 bg-red-950/50 border border-red-900 rounded-md flex items-start gap-2 text-red-500 text-sm">
                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <p>{errorMsg}</p>
                    </div>
                )}
             </CardContent>
          </Card>
        </div>

        {/* Console / Output Main Area */}
        <div className="md:col-span-2 space-y-6">
            <Card className="bg-[#0c0c0e] border-zinc-800 h-[500px] flex flex-col">
                <CardHeader className="py-3 border-b border-zinc-800 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm font-mono text-zinc-500 uppercase flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-500"></span>
                        STDOUT logs
                    </CardTitle>
                    {status === "completed" && (
                        <Button size="sm" onClick={handleDownload} className="h-7 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-100">Download .MD</Button>
                    )}
                </CardHeader>
                <CardContent className="flex-1 p-0 overflow-hidden text-zinc-300">
                    <ScrollArea className="h-[450px] w-full p-4" ref={scrollRef}>
                        <div className="font-mono text-xs whitespace-pre-wrap flex flex-col gap-1 tracking-tight">
                            {logs.length === 0 && status === "idle" && (
                                <span className="text-zinc-600">Waiting for job to start...</span>
                            )}
                            {logs.map((log, i) => (
                                <span key={i} className="text-zinc-400">{log}</span>
                            ))}
                            {status === "processing" && (
                                <span className="text-zinc-500 flex items-center gap-2 animate-pulse mt-2">
                                    <span className="w-1.5 h-1.5 bg-zinc-500 rounded-full"></span> Processing GPU Tensors...
                                </span>
                            )}
                        </div>
                    </ScrollArea>
                </CardContent>
            </Card>

            {status === "completed" && markdown && (
                 <Card className="bg-zinc-950 border-zinc-800 border-l-4 border-l-green-500">
                    <CardHeader>
                       <CardTitle className="flex items-center gap-2 text-green-500"><CheckCircle2 className="w-5 h-5"/> Conversion Successful</CardTitle>
                       <CardDescription className="text-zinc-400">Extracted {markdown.length.toLocaleString()} characters.</CardDescription>
                    </CardHeader>
                 </Card>
            )}
        </div>

      </div>
    </main>
  );
}
