

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Menu, Sparkles, Zap } from 'lucide-react';
import FileUpload from './components/FileUpload';
import ConversionProgress from './components/ConversionProgress';
import AudioPlayer from './components/AudioPlayer';
import HistorySidebar from './components/HistorySidebar';

// Configure axios base URL
// Configure axios base URL
axios.defaults.baseURL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// Session ID Management
const getSessionId = () => {
    let sessionId = sessionStorage.getItem('aurora_session_id');
    if (!sessionId) {
        sessionId = crypto.randomUUID();
        sessionStorage.setItem('aurora_session_id', sessionId);
    }
    return sessionId;
};

// Add Session ID to all requests
axios.interceptors.request.use(config => {
    config.headers['X-Session-ID'] = getSessionId();
    return config;
});


function App() {
    const [file, setFile] = useState(null);
    const [taskId, setTaskId] = useState(null);
    const [status, setStatus] = useState(null); // 'queued', 'processing', 'completed', 'failed'
    const [progress, setProgress] = useState(0);
    const [message, setMessage] = useState('');
    const [logs, setLogs] = useState([]); // New: detailed logs
    const [audioUrl, setAudioUrl] = useState(null);
    const [isHistoryOpen, setIsHistoryOpen] = useState(false);
    const [history, setHistory] = useState([]);
    const [engine, setEngine] = useState('edge'); // 'google' or 'edge'
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchHistory();
    }, []);

    useEffect(() => {
        let interval;
        if (taskId && status !== 'completed' && status !== 'failed') {
            interval = setInterval(checkStatus, 1000); // Faster polling
        }
        return () => clearInterval(interval);
    }, [taskId, status]);

    const fetchHistory = async () => {
        try {
            const response = await axios.get('/history');
            setHistory(response.data);
        } catch (err) {
            console.error('Failed to fetch history', err);
        }
    };

    const handleFileSelect = async (selectedFile) => {
        setFile(selectedFile);
        setError(null);
        setLogs([]);

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('engine', engine);

        try {
            const response = await axios.post('/upload', formData);
            setTaskId(response.data.task_id);
            setStatus('queued');
            setProgress(0);
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Upload successful. Task ID: ${response.data.task_id}`]);
        } catch (err) {
            setError(err.response?.data?.error || 'Upload failed');
        }
    };

    const checkStatus = async () => {
        if (!taskId) return;

        try {
            const response = await axios.get(`/status/${taskId}`);
            const data = response.data;

            setStatus(data.status);
            setProgress(data.progress);

            if (data.message !== message) {
                setMessage(data.message);
                setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${data.message}`]);
            }

            if (data.status === 'completed') {
                setAudioUrl(`http://localhost:5000/download/${taskId}`);
                fetchHistory();
            } else if (data.status === 'failed') {
                setError(data.message);
            }
        } catch (err) {
            console.error('Status check failed', err);
        }
    };

    const handleHistorySelect = (item) => {
        setAudioUrl(item.url || `${axios.defaults.baseURL}/download/${item.id}`); // Handle full URL or fall back
        setStatus('completed');
        setMessage('Loaded from history');
        setProgress(100);
        setIsHistoryOpen(false);
    };

    const handleClearSession = async () => {
        if (!confirm('Are you sure you want to clear your session history? This will delete all converted files.')) return;
        try {
            await axios.post('/cleanup-session');
            setHistory([]);
            setAudioUrl(null);
            setTaskId(null);
            setStatus(null);
            setFile(null);
            setIsHistoryOpen(false);
        } catch (err) {
            console.error('Failed to clear session', err);
        }
    };


    return (
        <div className="min-h-screen flex flex-col items-center justify-center p-6 relative overflow-hidden bg-background">

            {/* Header - Centered */}
            <header className="text-center mb-12 animate-fade-in">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-surface border border-border mb-6 shadow-xl overflow-hidden p-3">
                    <img src="/aurora_icon.svg" alt="Aurora Icon" className="w-full h-full object-contain" />
                </div>
                <h1 className="text-4xl font-bold tracking-tight mb-2 text-primary">
                    Aurora
                </h1>
                <p className="text-muted text-lg">Transform documents into natural speech</p>
            </header>

            {/* Main Content - Centered Container */}
            <main className="w-full max-w-xl space-y-8 animate-slide-up relative z-10">

                {/* Engine Toggle - Centered */}
                {!taskId && !audioUrl && (
                    <div className="flex justify-center flex-col items-center gap-8">
                        <div className="bg-surface p-1 rounded-xl border border-border inline-flex shadow-lg">
                            <button
                                onClick={() => setEngine('edge')}
                                className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${engine === 'edge'
                                    ? 'bg-secondary text-secondary-foreground shadow-sm'
                                    : 'text-muted hover:text-primary hover:bg-white/5'
                                    }`}
                            >
                                <Zap className="w-4 h-4" />
                                <span>Aurora Flow</span>
                            </button>
                            <button
                                onClick={() => setEngine('google')}
                                className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${engine === 'google'
                                    ? 'bg-primary text-primary-foreground shadow-sm'
                                    : 'text-muted hover:text-primary hover:bg-white/5'
                                    }`}
                            >
                                <Sparkles className="w-4 h-4" />
                                <span>Premium Journey</span>
                            </button>
                        </div>

                        {engine === 'google' && (
                            <div className="w-full max-w-md p-8 rounded-2xl bg-surface/50 border border-border backdrop-blur-sm text-center animate-fade-in">
                                <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-primary/10 mb-4">
                                    <Sparkles className="w-6 h-6 text-primary" />
                                </div>
                                <h3 className="text-xl font-semibold text-primary mb-2">Coming Soon</h3>
                                <p className="text-muted">The Premium Journey experience is currently under development. Stay tuned for enhanced narration features!</p>
                            </div>
                        )}
                    </div>
                )}

                {/* Upload Area */}
                {!taskId && !audioUrl && (
                    <FileUpload onFileSelect={handleFileSelect} />
                )}

                {/* Progress */}
                {(taskId || status) && status !== 'completed' && (
                    <ConversionProgress
                        status={status}
                        progress={progress}
                        message={message}
                        logs={logs}
                        error={error}
                    />
                )}

                {/* Player */}
                {audioUrl && (
                    <div className="space-y-6">
                        <AudioPlayer audioUrl={audioUrl} filename={file?.name || 'Audiobook'} />
                        <div className="text-center">
                            <button
                                onClick={() => {
                                    setTaskId(null);
                                    setStatus(null);
                                    setAudioUrl(null);
                                    setFile(null);
                                    setLogs([]);
                                }}
                                className="btn btn-secondary"
                            >
                                Convert Another File
                            </button>
                        </div>
                    </div>
                )}
            </main>

            {/* History Button - Fixed Bottom Right or Top Right? User asked for centered, but history is usually auxiliary. Let's put it top right but subtle. */}
            <div className="fixed top-6 right-6">
                <button
                    onClick={() => setIsHistoryOpen(true)}
                    className="btn btn-ghost p-3 rounded-full"
                    title="History"
                >
                    <Menu className="w-6 h-6" />
                </button>
            </div>

            <HistorySidebar
                isOpen={isHistoryOpen}
                onClose={() => setIsHistoryOpen(false)}
                history={history}
                onSelect={handleHistorySelect}
                onClear={handleClearSession}
            />

        </div>
    );
}

export default App;
