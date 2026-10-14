import { useEffect, useRef, useState } from "react";
import { AudioLines, Check, FileAudio2, Mic, Trash2, Upload, X } from "lucide-react";

const MAX_AUDIO_SIZE = 25 * 1024 * 1024;
const ACCEPTED_AUDIO_EXTENSIONS = /\.(aac|flac|m4a|mp3|oga|ogg|wav|weba|webm)$/i;
const RECORDING_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

type VoiceInputProps = {
  onAudioChange?: (file: File | null) => void;
};

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainingSeconds = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}

function formatFileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getRecordingMimeType(): string {
  return RECORDING_MIME_TYPES.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? "";
}

export default function VoiceInput({ onAudioChange }: VoiceInputProps) {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (!isRecording) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isRecording]);

  useEffect(() => () => {
    recorderRef.current?.removeEventListener("stop", handleRecordingStop);
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
    }
  }, []);

  function handleRecordingStop() {
    const recorder = recorderRef.current;
    if (!recorder) {
      return;
    }

    const recordedBlob = new Blob(recordingChunksRef.current, {
      type: recorder.mimeType || "audio/webm",
    });
    recordingChunksRef.current = [];
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setIsRecording(false);

    if (recordedBlob.size === 0) {
      setError("We couldn’t save that recording. Please try again.");
      return;
    }

    const extension = recordedBlob.type.includes("mp4") ? "m4a" : recordedBlob.type.includes("ogg") ? "ogg" : "webm";
    const recording = new File([recordedBlob], `voice-note-${Date.now()}.${extension}`, {
      type: recordedBlob.type,
    });
    setAudio(recording);
  }

  function setAudio(file: File | null) {
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
    }

    const nextUrl = file ? URL.createObjectURL(file) : null;
    audioUrlRef.current = nextUrl;
    setAudioUrl(nextUrl);
    setAudioFile(file);
    onAudioChange?.(file);
  }

  function validateAudio(file: File): string | null {
    if (file.size > MAX_AUDIO_SIZE) {
      return "That file is too large. Choose an audio file under 25 MB.";
    }

    if (file.size === 0) {
      return "That audio file is empty. Choose another file.";
    }

    const mimeType = file.type.toLowerCase();
    if (
      (mimeType && !mimeType.startsWith("audio/")) ||
      (!mimeType && !ACCEPTED_AUDIO_EXTENSIONS.test(file.name))
    ) {
      return "That file doesn’t look like audio. Try MP3, M4A, WAV, OGG, or WEBM.";
    }

    return null;
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    const validationError = validateAudio(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setRecordingSeconds(0);
    setAudio(file);
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !("MediaRecorder" in window)) {
      setError("Audio recording isn’t supported in this browser. You can upload an audio file instead.");
      return;
    }

    setError(null);
    setRecordingSeconds(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getRecordingMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recordingChunksRef.current = [];
      recorderRef.current = recorder;
      streamRef.current = stream;
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          recordingChunksRef.current.push(event.data);
        }
      });
      recorder.addEventListener("stop", handleRecordingStop, { once: true });
      recorder.start();
      setIsRecording(true);
    } catch (recordingError) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setError(
        recordingError instanceof DOMException && recordingError.name === "NotAllowedError"
          ? "Microphone access was blocked. Allow access in your browser settings, or upload an audio file."
          : "We couldn’t access your microphone. Check your device settings or upload an audio file.",
      );
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
    }
  }

  function removeAudio() {
    setAudio(null);
    setRecordingSeconds(0);
    setError(null);
  }

  return (
    <section className="voice-input" aria-labelledby="voice-input-title">
      <div className="voice-input-heading">
        <div>
          <h3 id="voice-input-title">Rather talk it through?</h3>
          <p>Record a voice note or add an audio file.</p>
        </div>
        <span className="voice-heading-icon" aria-hidden="true"><AudioLines size={19} /></span>
      </div>

      {audioFile ? (
        <div className="audio-ready-card">
          <div className="audio-file-icon"><FileAudio2 size={19} /></div>
          <div className="audio-file-info">
            <strong title={audioFile.name}>{audioFile.name}</strong>
            <span><Check size={13} /> Ready to preview <span className="audio-file-separator">·</span> {formatFileSize(audioFile.size)}</span>
          </div>
          <button className="audio-remove-button" type="button" onClick={removeAudio} aria-label="Remove audio">
            <Trash2 size={16} />
          </button>
          {audioUrl && <audio className="audio-preview" controls src={audioUrl} aria-label="Preview your audio" />}
        </div>
      ) : (
        <div className={`voice-controls ${isRecording ? "is-recording" : ""}`}>
          <button
            className={`record-button ${isRecording ? "record-button-active" : ""}`}
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            aria-label={isRecording ? "Stop recording" : "Start recording"}
          >
            {isRecording ? <span className="stop-square" /> : <Mic size={18} />}
          </button>
          <div className="recording-copy" aria-live="polite">
            <strong>{isRecording ? "Recording your voice note" : "Record a voice note"}</strong>
            <span>{isRecording ? "Tap the button when you’re done" : "Use your microphone · No more than 25 MB"}</span>
          </div>
          {isRecording ? (
            <div className="recording-timer"><span className="recording-pulse" />{formatTime(recordingSeconds)}</div>
          ) : (
            <button
              className="upload-button"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Choose an audio file"
            >
              <Upload size={15} /> Browse
            </button>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        className="visually-hidden"
        type="file"
        accept="audio/*,.aac,.flac,.m4a,.mp3,.oga,.ogg,.wav,.weba,.webm"
        onChange={handleFileChange}
        aria-label="Choose an audio file"
      />
      {error && (
        <p className="voice-error" role="alert">
          <X size={15} /> {error}
        </p>
      )}
      <p className="voice-file-hint">MP3, M4A, WAV, OGG, or WEBM <span>·</span> Max 25 MB</p>
    </section>
  );
}
