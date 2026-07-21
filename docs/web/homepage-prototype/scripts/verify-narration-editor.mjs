import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  EDITOR_MEDIA,
  INITIAL_CLIPS,
  parseSrt,
  findCue,
} from '../src/features/narration-editor/editor-data.js';

const cues = parseSrt('1\n00:00:01,000 --> 00:00:03,000\n古墓入口\n');
assert.deepEqual(cues, [{ start: 1, end: 3, text: '古墓入口' }]);
assert.equal(findCue(cues, 2).text, '古墓入口');
assert.equal(findCue(cues, 3), null);
assert.equal(INITIAL_CLIPS.filter((clip) => clip.trackId === 'video').length, 3);
assert.ok(EDITOR_MEDIA.videos.every((url) => url.startsWith('/media/narration-editor/')));
assert.ok(EDITOR_MEDIA.audio.startsWith('/media/narration-editor/'));
assert.ok(EDITOR_MEDIA.subtitles.startsWith('/media/narration-editor/'));

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const editorSource = await readFile(
  path.join(projectRoot, 'src/features/narration-editor/NarrationEditor.jsx'),
  'utf8',
);
assert.match(
  editorSource,
  /<Link\s+className="editor-export"\s+to="\/dashboard\/projects\/overlord\/result">生成视频<\/Link>/,
  '生成视频应为指向项目结果页的可点击 Link',
);

console.log('PASS: narration editor data');
