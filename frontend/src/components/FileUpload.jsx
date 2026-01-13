import React, { useCallback } from 'react';
import { Upload, FileText } from 'lucide-react';
import { motion } from 'framer-motion';

const FileUpload = ({ onFileSelect }) => {
    const handleDrop = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();

        const files = e.dataTransfer.files;
        if (files && files.length > 0 && files[0].type === 'application/pdf') {
            onFileSelect(files[0]);
        }
    }, [onFileSelect]);

    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleFileInput = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            onFileSelect(e.target.files[0]);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full"
        >
            <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                className="glass-panel p-12 text-center border-2 border-dashed border-border hover:border-primary/50 hover:bg-surface-highlight/50 transition-all duration-300 cursor-pointer group"
                onClick={() => document.getElementById('fileInput').click()}
            >
                <input
                    type="file"
                    id="fileInput"
                    className="hidden"
                    accept=".pdf"
                    onChange={handleFileInput}
                />

                <div className="w-16 h-16 mx-auto bg-surface rounded-2xl flex items-center justify-center mb-6 shadow-lg group-hover:scale-110 transition-transform duration-300 border border-border">
                    <Upload className="w-8 h-8 text-primary" />
                </div>

                <h3 className="text-xl font-semibold mb-2 text-primary">
                    Upload PDF
                </h3>
                <p className="text-muted mb-6 text-sm">
                    Drag and drop or click to browse
                </p>

                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-xs text-muted">
                    <FileText className="w-3 h-3" />
                    <span>Max 100MB</span>
                </div>
            </div>
        </motion.div>
    );
};

export default FileUpload;
