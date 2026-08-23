import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import {
  downloadWhisperModel,
  installWhisperCpp,
  toCaptions,
  transcribe,
} from '@remotion/install-whisper-cpp';

const [inputArgument, outputArgument] = process.argv.slice(2);
if (!inputArgument || !outputArgument) {
  throw new Error('用法：node align.mjs <voice.wav> <captions.json>');
}

const rendererRoot = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(.:)/, '$1'));
const inputPath = path.resolve(inputArgument);
const outputPath = path.resolve(outputArgument);
const cacheRoot = path.join(rendererRoot, '.cache');
const whisperPath = path.join(cacheRoot, 'whisper.cpp-1.5.5');
const modelFolder = path.join(cacheRoot, 'models');
const convertedPath = path.join(path.dirname(outputPath), 'voice.alignment-16k.wav');
const whisperVersion = '1.5.5';
const model = process.env.INFOGRAPHIC_WHISPER_MODEL || 'medium';

fs.mkdirSync(cacheRoot, {recursive: true});
fs.mkdirSync(modelFolder, {recursive: true});
const conversion = spawnSync('ffmpeg', [
  '-y', '-hide_banner', '-loglevel', 'error', '-i', inputPath,
  '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', convertedPath,
], {encoding: 'utf8'});
if (conversion.status !== 0) {
  throw new Error(`旁白转换为 16kHz PCM 失败：${conversion.stderr || conversion.stdout}`);
}

const durationProbe = spawnSync('ffprobe', [
  '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nk=1:nw=1', convertedPath,
], {encoding: 'utf8'});
if (durationProbe.status !== 0) {
  throw new Error(`无法读取旁白时长：${durationProbe.stderr || durationProbe.stdout}`);
}
const audioDurationMs = Math.max(1, Math.round(Number(durationProbe.stdout.trim()) * 1000));
const silenceProbe = spawnSync('ffmpeg', [
  '-hide_banner', '-i', convertedPath,
  '-af', 'silencedetect=noise=-40dB:d=0.12',
  '-f', 'null', process.platform === 'win32' ? 'NUL' : '/dev/null',
], {encoding: 'utf8'});
const silenceLog = `${silenceProbe.stderr || ''}\n${silenceProbe.stdout || ''}`;
const silenceEvents = [...silenceLog.matchAll(/silence_(start|end):\s*([0-9.]+)/g)]
  .map((match) => ({kind: match[1], atMs: Math.max(0, Math.round(Number(match[2]) * 1000))}));
const speechSegments = [];
let speechCursorMs = 0;
for (const event of silenceEvents) {
  if (event.kind === 'start') {
    if (event.atMs - speechCursorMs >= 60) {
      speechSegments.push({startMs: speechCursorMs, endMs: Math.min(audioDurationMs, event.atMs)});
    }
  } else {
    speechCursorMs = Math.max(speechCursorMs, event.atMs);
  }
}
if (audioDurationMs - speechCursorMs >= 60) {
  speechSegments.push({startMs: speechCursorMs, endMs: audioDurationMs});
}

await installWhisperCpp({
  to: whisperPath,
  version: whisperVersion,
  printOutput: true,
});
await downloadWhisperModel({
  model,
  folder: modelFolder,
  printOutput: true,
});

const whisperCppOutput = await transcribe({
  inputPath: convertedPath,
  whisperPath,
  whisperCppVersion: whisperVersion,
  model,
  modelFolder,
  language: 'zh',
  translateToEnglish: false,
  tokenLevelTimestamps: true,
  splitOnWord: true,
  printOutput: false,
});
const {captions} = toCaptions({whisperCppOutput});
if (!captions.length) {
  throw new Error('本地语音识别没有返回任何 token 时间戳');
}
fs.writeFileSync(outputPath, JSON.stringify({
  schemaVersion: 2,
  engine: 'whisper.cpp',
  whisperVersion,
  model,
  segmentation: 'word-boundary-dtw-audio-v2',
  audioDurationMs,
  speechSegments,
  captions,
}, null, 2));
