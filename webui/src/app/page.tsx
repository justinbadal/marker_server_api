"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Label } from "@/components/ui/label";
import {
  Terminal, Upload, Play, Settings, CheckCircle2, AlertCircle,
  Activity, FileText, ChevronDown, ChevronUp, Code, Eye, X, File, FolderOpen, Download,
} from "lucide-react";

const DEFAULT_API_URL = process.env.NEXT_PUBLIC_MARKER_API_BASE_URL || "/api";
const SUPPORTED_FILE_ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,.pptx,.docx,.xlsx,.html,.htm,.epub";
const SUPPORTED_FILE_LABEL = "PDF, images, PPTX, DOCX, XLSX, HTML, EPUB";

// ─── types ───────────────────────────────────────────────────────────────────
interface JobFile { name: string; size: number; }
interface BatchItem {
  item_id: string;
  original_filename: string;
  status: string;
  error?: string;
  files?: JobFile[];
  logs?: string[];
  artifact_summary?: {
    generated_file_count?: number;
    image_file_count?: number;
  };
}
interface Options {
  page_range: string;
  force_ocr: boolean;
  disable_image_extraction: boolean;
  paginate_output: boolean;
  keep_pageheader_in_output: boolean;
  html_tables_in_markdown: boolean;
  disable_links: boolean;
  strip_existing_ocr: boolean;
  max_concurrency: number;
  highres_image_dpi: number;
}

interface BatchStatusResponse {
  status: string;
  total_items: number;
  completed_items: number;
  items: BatchItem[];
}

function fmt(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

// ─── Markdown Modal ───────────────────────────────────────────────────────────
function MarkdownModal({ markdown, onClose }: { markdown: string; onClose: () => void }) {
  const [rendered, setRendered] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-zinc-950 border border-zinc-800 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-green-400" />
            <span className="font-mono text-sm text-zinc-300">Conversion Output</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setRendered(false)}
              className={`h-7 text-xs font-mono gap-1 ${!rendered ? "bg-zinc-800 text-zinc-100" : "text-zinc-500"}`}
            >
              <Code className="w-3 h-3" /> Raw
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setRendered(true)}
              className={`h-7 text-xs font-mono gap-1 ${rendered ? "bg-zinc-800 text-zinc-100" : "text-zinc-500"}`}
            >
              <Eye className="w-3 h-3" /> Rendered
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCopy}
              className={`h-7 text-xs font-mono gap-1 ${copied ? "bg-green-950 text-green-300" : "text-zinc-500 hover:text-zinc-100"}`}
            >
              {copied ? "Copied" : "Copy Markdown"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onClose} className="h-7 w-7 p-0 text-zinc-500 hover:text-zinc-100">
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-5 custom-scrollbar">
          {rendered ? (
            <div className="prose prose-invert prose-zinc max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
            </div>
          ) : (
            <pre className="font-mono text-xs text-zinc-300 whitespace-pre-wrap">{markdown}</pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Status Bar ───────────────────────────────────────────────────────────────
function StatusBar({ apiUrl, apiKey }: { apiUrl: string; apiKey: string }) {
  const [health, setHealth] = useState<{ status: string; marker_available: boolean; llm_url: string; llm_models?: string[] } | null>(null);
  const [loading, setLoading] = useState(true);

  const check = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiUrl}/health`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      setHealth(await res.json());
    } catch {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, [apiUrl, apiKey]);

  useEffect(() => {
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, [check]);

  const online = health?.status === "ok";
  const modelLabel = health?.llm_models?.length
    ? health.llm_models.join(", ")
    : "unknown";
  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs font-mono">
      <div className="flex items-center gap-2">
        <Activity className="w-3 h-3 text-zinc-500" />
        <span className="text-zinc-500 uppercase tracking-widest">API</span>
        {loading ? (
          <span className="text-zinc-600 animate-pulse">checking...</span>
        ) : online ? (
          <span className="flex items-center gap-1.5 text-green-400"><span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />Online</span>
        ) : (
          <span className="flex items-center gap-1.5 text-red-400"><span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />Unreachable</span>
        )}
      </div>
      {online && (
        <>
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-500">marker_single: {health?.marker_available ? <span className="text-green-400">ready</span> : <span className="text-red-400">missing</span>}</span>
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-600 truncate max-w-xs">Models: {modelLabel}</span>
        </>
      )}
      <button onClick={check} className="ml-auto text-zinc-600 hover:text-zinc-400 transition-colors">↻ refresh</button>
    </div>
  );
}

// ─── Options Panel ────────────────────────────────────────────────────────────
const DEFAULT_OPTIONS: Options = {
  page_range: "",
  force_ocr: false,
  disable_image_extraction: false,
  paginate_output: false,
  keep_pageheader_in_output: false,
  html_tables_in_markdown: false,
  disable_links: false,
  strip_existing_ocr: false,
  max_concurrency: 4,
  highres_image_dpi: 192,
};

function OptionsPanel({ opts, setOpts }: { opts: Options; setOpts: (o: Options) => void }) {
  const [open, setOpen] = useState(false);
  const toggleBool = (k: keyof Options) => setOpts({ ...opts, [k]: !opts[k as keyof Options] });
  const setNum = (k: keyof Options, v: number) => setOpts({ ...opts, [k]: v });
  const setStr = (k: keyof Options, v: string) => setOpts({ ...opts, [k]: v });

  return (
    <Card className="bg-zinc-950 border-zinc-800">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-zinc-100 hover:bg-zinc-900/50 transition-colors rounded-xl"
      >
        <span className="flex items-center gap-2 text-sm font-medium"><Settings className="w-4 h-4" /> Options</span>
        {open ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
      </button>
      {open && (
        <CardContent className="pt-0 pb-4 space-y-4">
          <div className="space-y-1">
            <Label className="text-zinc-400 text-xs">Page Range <span className="text-zinc-600">(e.g. 0,5-10,20)</span></Label>
            <Input
              value={opts.page_range}
              onChange={e => setStr("page_range", e.target.value)}
              placeholder="All pages"
              className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-xs h-8"
            />
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {([
              ["force_ocr", "Force OCR"],
              ["disable_image_extraction", "No Images"],
              ["paginate_output", "Paginate Output"],
              ["keep_pageheader_in_output", "Keep Page Headers"],
              ["html_tables_in_markdown", "HTML Tables"],
              ["disable_links", "Disable Links"],
              ["strip_existing_ocr", "Strip Existing OCR"],
            ] as [keyof Options, string][]).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={!!opts[key]}
                  onChange={() => toggleBool(key)}
                  className="accent-zinc-400"
                />
                <span className="text-xs text-zinc-400 group-hover:text-zinc-300">{label}</span>
              </label>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-zinc-400 text-xs">Max Concurrency</Label>
              <Input
                type="number" min={1} max={16}
                value={opts.max_concurrency}
                onChange={e => setNum("max_concurrency", parseInt(e.target.value)||4)}
                className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-xs h-8"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-zinc-400 text-xs">Highres DPI</Label>
              <Input
                type="number" min={96} max={400}
                value={opts.highres_image_dpi}
                onChange={e => setNum("highres_image_dpi", parseInt(e.target.value)||192)}
                className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-xs h-8"
              />
            </div>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function Home() {
  const apiUrl = DEFAULT_API_URL;
  const [apiKey, setApiKey] = useState("my-secret-token");
  const [files, setFiles] = useState<File[]>([]);
  const [opts, setOpts] = useState<Options>(DEFAULT_OPTIONS);

  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "completed" | "error">("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [jobFiles, setJobFiles] = useState<JobFile[]>([]);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [isBatchJob, setIsBatchJob] = useState(false);
  const [openItems, setOpenItems] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      const vp = scrollRef.current.querySelector("[data-radix-scroll-area-viewport]");
      if (vp) vp.scrollTop = vp.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute("webkitdirectory", "");
      folderInputRef.current.setAttribute("directory", "");
    }
  }, []);

  const selectedLabel = files.length === 0
    ? "No files selected"
    : files.length === 1
      ? files[0].name
      : `${files.length} files selected`;

  // Polling: status + files
  useEffect(() => {
    if (status !== "processing" || !jobId) return;
    const id = setInterval(async () => {
      try {
        const statusPath = isBatchJob ? `${apiUrl}/batch/status/${jobId}` : `${apiUrl}/status/${jobId}`;
        const res = await fetch(statusPath, {
          headers: { Authorization: `Bearer ${apiKey}` },
        });
        const data = await res.json();
        if (data.logs?.length) setLogs(data.logs);

        if (data.status === "completed" || data.status === "completed_with_errors") {
          setStatus("completed");
          if (isBatchJob) {
            setBatchItems(data.items ?? []);
          } else {
            const mdRes = await fetch(`${apiUrl}/download/${jobId}`, {
              headers: { Authorization: `Bearer ${apiKey}` },
            });
            setMarkdown(await mdRes.text());
            const fRes = await fetch(`${apiUrl}/files/${jobId}`, {
              headers: { Authorization: `Bearer ${apiKey}` },
            });
            const fData = await fRes.json();
            setJobFiles(fData.files ?? []);
          }
        } else if (data.status === "failed") {
          setStatus("error");
          setErrorMsg(data.error || "Conversion failed");
        } else if (isBatchJob) {
          setBatchItems(data.items ?? []);
        }
      } catch {}
    }, 2000);
    return () => clearInterval(id);
  }, [status, jobId, apiUrl, apiKey, isBatchJob]);

  const handleSelection = (selected: FileList | null) => {
    setFiles(selected ? Array.from(selected) : []);
  };

  const handleStart = async () => {
    if (files.length === 0) return;
    setStatus("uploading");
    setLogs([]);
    setMarkdown("");
    setErrorMsg("");
    setJobFiles([]);
    setBatchItems([]);
    setOpenItems({});
    const batchMode = files.length > 1;
    setIsBatchJob(batchMode);
    const fd = new FormData();
    if (batchMode) {
      files.forEach((selectedFile) => fd.append("files", selectedFile));
    } else {
      fd.append("file", files[0]);
    }
    Object.entries(opts).forEach(([k, v]) => {
      if (v !== undefined && v !== null) {
        fd.append(k, v.toString());
      }
    });
    try {
      const res = await fetch(`${apiUrl}/${batchMode ? "convert/batch" : "convert/async"}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "API Error");
      setJobId(data.job_id);
      setStatus("processing");
      const activeOpts = Object.entries(opts).filter(([k, v]) => v !== false && v !== "" && v !== DEFAULT_OPTIONS[k as keyof Options]).map(([k,v]) => `${k}=${v}`);
      setLogs([
        `> Job started: ${data.job_id}`,
        `> Mode: ${batchMode ? `batch (${files.length} files, max 4 at once)` : "single file"}`,
        ...(activeOpts.length ? [`> Options: ${activeOpts.join(", ")}`] : []),
      ]);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Conversion failed");
      setStatus("error");
    }
  };

  const handleDownload = async () => {
    if (!jobId || isBatchJob) return;
    const res = await fetch(`${apiUrl}/download/${jobId}`, { headers: { Authorization: `Bearer ${apiKey}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const fileBaseName = files[0]?.name ? files[0].name.replace(/\.[^.]+$/, "") : "converted";
    a.href = url; a.download = `${fileBaseName}.md`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const handleBatchDownload = async () => {
    if (!jobId || !isBatchJob) return;
    const res = await fetch(`${apiUrl}/batch/download/${jobId}`, { headers: { Authorization: `Bearer ${apiKey}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${jobId}.zip`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const handleBatchItemDownload = async (item: BatchItem) => {
    if (!jobId) return;
    const res = await fetch(`${apiUrl}/batch/download/${jobId}/${item.item_id}`, { headers: { Authorization: `Bearer ${apiKey}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${item.original_filename.replace(/\.[^.]+$/, "")}.md`;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const handlePreviewBatchItem = async (item: BatchItem) => {
    if (!jobId) return;
    const res = await fetch(`${apiUrl}/batch/download/${jobId}/${item.item_id}`, { headers: { Authorization: `Bearer ${apiKey}` } });
    setMarkdown(await res.text());
    setModalOpen(true);
  };

  const toggleItemOpen = (itemId: string) => {
    setOpenItems((prev) => ({ ...prev, [itemId]: !prev[itemId] }));
  };

  const busy = status === "uploading" || status === "processing";
  const batchCompletedCount = batchItems.filter((item) => item.status === "completed").length;
  const batchFailedCount = batchItems.filter((item) => item.status === "failed").length;
  const batchProcessingCount = batchItems.filter((item) => item.status === "processing").length;
  const batchPendingCount = batchItems.filter((item) => item.status === "pending").length;

  const getBatchStatusTone = (itemStatus: string) => {
    if (itemStatus === "completed") return "text-green-400";
    if (itemStatus === "failed") return "text-red-400";
    if (itemStatus === "processing") return "text-amber-400";
    return "text-zinc-500";
  };

  return (
    <>
      {modalOpen && markdown && <MarkdownModal markdown={markdown} onClose={() => setModalOpen(false)} />}
      <main className="container mx-auto p-6 max-w-6xl space-y-4">

        {/* Header */}
        <div className="flex items-center gap-3 pb-3 border-b border-zinc-800 text-zinc-100">
          <Terminal className="w-7 h-7" />
          <h1 className="text-2xl font-bold tracking-tight">MARKER STUDIO</h1>
        </div>

        {/* Status Bar */}
        <StatusBar apiUrl={apiUrl} apiKey={apiKey} />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">

          {/* Left Sidebar */}
          <div className="space-y-4">
            {/* Connection */}
            <Card className="bg-zinc-950 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-zinc-100 text-sm"><Settings className="w-4 h-4" /> Connection</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1">
                  <Label className="text-zinc-400 text-xs">Bearer Token</Label>
                  <Input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                    className="bg-zinc-900 border-zinc-800 text-zinc-300 font-mono text-xs h-8" />
                </div>
              </CardContent>
            </Card>

            {/* Payload */}
            <Card className="bg-zinc-950 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-zinc-100 text-sm"><Upload className="w-4 h-4" /> Payload</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={SUPPORTED_FILE_ACCEPT}
                  multiple
                  onChange={e => handleSelection(e.target.files)}
                  className="hidden"
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  accept={SUPPORTED_FILE_ACCEPT}
                  multiple
                  onChange={e => handleSelection(e.target.files)}
                  className="hidden"
                />
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex-1 border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
                  >
                    <File className="w-3.5 h-3.5 mr-1.5" /> Choose Files
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => folderInputRef.current?.click()}
                    className="flex-1 border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"
                  >
                    <FolderOpen className="w-3.5 h-3.5 mr-1.5" /> Choose Folder
                  </Button>
                </div>
                <div className="rounded-md border border-zinc-800 bg-zinc-900/70 px-3 py-2">
                  <p className="text-xs font-mono text-zinc-300">{selectedLabel}</p>
                  {files.length > 0 && (
                    <p className="mt-1 text-[11px] text-zinc-500">
                      {files.slice(0, 4).map((selected) => selected.name).join(", ")}
                      {files.length > 4 ? ` + ${files.length - 4} more` : ""}
                    </p>
                  )}
                </div>
                <p className="text-[11px] text-zinc-500">
                  Accepts {SUPPORTED_FILE_LABEL}. Batch jobs process up to 4 files at a time.
                </p>
                <Button onClick={handleStart} disabled={files.length === 0 || busy}
                  className="w-full bg-zinc-100 text-zinc-950 hover:bg-zinc-300 font-bold text-xs h-9">
                  {status === "uploading" ? "Uploading..." : busy ? "Converting..." : <><Play className="w-3.5 h-3.5 mr-1.5" />Start Conversion</>}
                </Button>
                {status === "error" && (
                  <div className="p-2.5 bg-red-950/50 border border-red-900 rounded-md flex items-start gap-2 text-red-400 text-xs">
                    <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />{errorMsg}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Options */}
            <OptionsPanel opts={opts} setOpts={setOpts} />
          </div>

          {/* Right — Console + Results */}
          <div className="md:col-span-2 space-y-4">

            {/* Console */}
            <Card className="bg-[#0a0a0c] border-zinc-800 flex flex-col" style={{ height: 420 }}>
              <CardHeader className="py-2.5 px-4 border-b border-zinc-800 flex flex-row items-center justify-between shrink-0">
                <CardTitle className="text-xs font-mono text-zinc-500 uppercase flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${busy ? "bg-amber-400 animate-pulse" : status === "completed" ? "bg-green-500" : status === "error" ? "bg-red-500" : "bg-zinc-600"}`} />
                  STDOUT
                </CardTitle>
                {status === "completed" && !isBatchJob && (
                  <Button size="sm" onClick={handleDownload}
                    className="h-6 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-100 px-2">
                    Download .MD
                  </Button>
                )}
              </CardHeader>
              <CardContent className="flex-1 p-0 overflow-hidden">
                <ScrollArea className="h-full w-full p-4" ref={scrollRef}>
                  <div className="font-mono text-xs whitespace-pre-wrap flex flex-col gap-0.5 tracking-tight">
                    {logs.length === 0 && status === "idle" && (
                      <span className="text-zinc-700">Waiting for job to start...</span>
                    )}
                    {logs.map((log, i) => <span key={i} className="text-zinc-400">{log}</span>)}
                    {busy && (
                      <span className="text-zinc-600 flex items-center gap-2 animate-pulse mt-2">
                        <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" /> Processing...
                      </span>
                    )}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Success Banner */}
            {status === "completed" && !isBatchJob && markdown && (
              <button
                onClick={() => setModalOpen(true)}
                className="w-full text-left"
              >
                <Card className="bg-zinc-950 border-zinc-800 border-l-4 border-l-green-500 hover:bg-zinc-900/80 transition-colors cursor-pointer">
                  <CardContent className="py-3 px-4 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                      <div>
                        <p className="text-green-400 text-sm font-semibold">Conversion Successful</p>
                        <p className="text-zinc-500 text-xs">
                          {markdown.length.toLocaleString()} characters extracted — <span className="text-zinc-400 underline underline-offset-2">click to view markdown</span>
                        </p>
                      </div>
                    </div>
                    <Eye className="w-4 h-4 text-zinc-600" />
                  </CardContent>
                </Card>
              </button>
            )}

            {/* File Listing */}
            {status === "completed" && !isBatchJob && jobFiles.length > 0 && (
              <Card className="bg-zinc-950 border-zinc-800">
                <CardHeader className="py-2.5 px-4 border-b border-zinc-800">
                  <CardTitle className="text-xs font-mono text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                    <File className="w-3.5 h-3.5" /> Extracted Files ({jobFiles.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-zinc-900">
                    {jobFiles.map(f => (
                      <div key={f.name} className="flex items-center justify-between px-4 py-2 hover:bg-zinc-900/50 transition-colors">
                        <span className="font-mono text-xs text-zinc-300 truncate max-w-xs">{f.name}</span>
                        <span className="font-mono text-xs text-zinc-600 shrink-0 ml-4">{fmt(f.size)}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {isBatchJob && batchItems.length > 0 && status !== "idle" && status !== "error" && (
              <Card className="bg-zinc-950 border-zinc-800">
                <CardHeader className="py-2.5 px-4 border-b border-zinc-800 flex flex-row items-center justify-between">
                  <div className="flex items-center gap-3">
                    <CardTitle className="text-xs font-mono text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                      <FolderOpen className="w-3.5 h-3.5" /> Batch Results ({batchItems.length})
                    </CardTitle>
                    <span className="text-[11px] font-mono text-zinc-500">
                      <span className="text-green-400">{batchCompletedCount} done</span>
                      {" • "}
                      <span className="text-amber-400">{batchProcessingCount} processing</span>
                      {" • "}
                      <span className="text-zinc-500">{batchPendingCount} pending</span>
                      {batchFailedCount > 0 ? <>{" • "}<span className="text-red-400">{batchFailedCount} failed</span></> : null}
                    </span>
                  </div>
                  {status === "completed" && (
                    <Button size="sm" onClick={handleBatchDownload}
                      className="h-6 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-100 px-2">
                      <Download className="w-3 h-3 mr-1" /> Bulk Download ZIP
                    </Button>
                  )}
                </CardHeader>
                <CardContent className="p-0">
                  <div className="divide-y divide-zinc-900">
                    {batchItems.map((item) => {
                      const isOpen = !!openItems[item.item_id];
                      const itemFiles = item.files ?? [];
                      return (
                        <div key={item.item_id}>
                          <button
                            type="button"
                            onClick={() => toggleItemOpen(item.item_id)}
                            className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-zinc-900/50 transition-colors"
                          >
                            <div>
                              <p className="font-mono text-xs text-zinc-200">{item.original_filename}</p>
                              <p className={`mt-1 text-[11px] ${getBatchStatusTone(item.status)}`}>
                                {item.status}
                                {item.artifact_summary?.generated_file_count ? ` • ${item.artifact_summary.generated_file_count} generated files` : ""}
                                {item.artifact_summary?.image_file_count ? ` • ${item.artifact_summary.image_file_count} images` : ""}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              {item.status === "completed" && (
                                <>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      void handlePreviewBatchItem(item);
                                    }}
                                    className="h-7 text-xs text-zinc-300 hover:text-zinc-100"
                                  >
                                    <Eye className="w-3 h-3 mr-1" /> Preview
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      void handleBatchItemDownload(item);
                                    }}
                                    className="h-7 text-xs text-zinc-300 hover:text-zinc-100"
                                  >
                                    <Download className="w-3 h-3 mr-1" /> Download
                                  </Button>
                                </>
                              )}
                              {isOpen ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
                            </div>
                          </button>
                          {isOpen && (
                            <div className="border-t border-zinc-900 bg-zinc-950/70 px-4 py-3">
                              {item.error && <p className="mb-2 text-xs text-red-400">{item.error}</p>}
                              {item.logs?.length ? (
                                <div className="mb-3 rounded-md bg-zinc-900 p-3">
                                  <div className="font-mono text-[11px] text-zinc-500">Recent logs</div>
                                  <div className="mt-2 space-y-1 font-mono text-[11px] text-zinc-400">
                                    {item.logs.map((logLine, index) => <div key={`${item.item_id}-${index}`}>{logLine}</div>)}
                                  </div>
                                </div>
                              ) : null}
                              {itemFiles.length > 0 ? (
                                <div className="space-y-2">
                                  {itemFiles.map((generatedFile) => (
                                    <div key={`${item.item_id}-${generatedFile.name}`} className="flex items-center justify-between rounded-md border border-zinc-900 px-3 py-2">
                                      <span className="font-mono text-xs text-zinc-300">{generatedFile.name}</span>
                                      <span className="font-mono text-xs text-zinc-600">{fmt(generatedFile.size)}</span>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-xs text-zinc-500">No generated files listed.</p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

          </div>
        </div>
      </main>
    </>
  );
}
