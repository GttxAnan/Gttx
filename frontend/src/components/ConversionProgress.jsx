import React from 'react';
import { motion } from 'framer-motion';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

const ConversionProgress = ({ status, progress, message, logs, error }) => {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full glass-panel p-6"
        >
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    {status === 'processing' && <Loader2 className="w-5 h-5 text-accent animate-spin" />}
                    {status === 'completed' && <CheckCircle className="w-5 h-5 text-green-500" />}
                    {status === 'failed' && <AlertCircle className="w-5 h-5 text-red-500" />}
                    <span className="font-medium text-primary">
                        {status === 'processing' ? 'Processing...' :
                            status === 'completed' ? 'Done' :
                                status === 'failed' ? 'Error' : 'Queued'}
                    </span>
                </div>
                <span className="font-mono font-bold text-muted text-sm">{Math.round(progress)}%</span>
            </div>

            <div className="h-2 bg-surface rounded-full overflow-hidden mb-6">
                <motion.div
                    className={`h-full ${status === 'failed' ? 'bg-red-500' : 'bg-primary'}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.5 }}
                />
            </div>

            {/* Terminal Log View */}
            <div className="bg-black rounded-lg p-4 font-mono text-xs h-40 overflow-y-auto border border-border shadow-inner custom-scrollbar">
                {logs && logs.map((log, index) => (
                    <div key={index} className="mb-1 text-zinc-400">
                        <span className="text-zinc-600 mr-2">{log.split(']')[0]}]</span>
                        <span>{log.split(']')[1]}</span>
                    </div>
                ))}
                {status === 'processing' && (
                    <div className="animate-pulse text-accent">_</div>
                )}
            </div>

            {error && (
                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                </div>
            )}
        </motion.div>
    );
};

export default ConversionProgress;
