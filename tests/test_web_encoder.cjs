// Run the actual browser worker in an isolated JS context, then inspect its MP3.
const assert = require('node:assert/strict');
const {readFileSync,writeFileSync,mkdtempSync,rmSync,rmdirSync} = require('node:fs');
const {join,resolve} = require('node:path');
const {tmpdir} = require('node:os');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const {test} = require('node:test');
const docs = resolve(__dirname, '../docs');

for (const mono of [true,false]) {
  test(`browser encoder produces decodable 48kbps ${mono ? 'mono' : 'stereo'} MP3`, async () => {
    const folder = mkdtempSync(join(tmpdir(), 'mp3-web-test-'));
    try {
      const messages = [];
      const context = vm.createContext({console,Blob,Float32Array,Int16Array,Uint8Array,Int8Array,Int32Array,Float64Array,ArrayBuffer,Math});
      context.self = {postMessage: message => messages.push(message)};
      context.importScripts = name => vm.runInContext(readFileSync(join(docs, name),'utf8'),context);
      vm.runInContext(readFileSync(join(docs,'encoder-worker.js'),'utf8'),context);
      const rate = 24000;
      const channels = [440,880].map(frequency => Float32Array.from({length:rate*3}, (_, i) => .3*Math.sin(2*Math.PI*frequency*i/rate)));
      context.self.onmessage({data:{channels,sampleRate:rate,bitrate:48,mono}});
      const result = messages.at(-1);
      assert.equal(result.type,'done',JSON.stringify(result));
      const file = join(folder,'encoded.mp3');
      writeFileSync(file, Buffer.from(await result.blob.arrayBuffer()));
      const info = JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file]));
      assert.equal(Number(info.streams[0].bit_rate),48000);
      assert.equal(info.streams[0].channels,mono ? 1 : 2);
      assert.ok(Math.abs(Number(info.format.duration)-3)<.15);
      assert.ok(result.blob.size<20000);
      assert.ok(messages.some(message => message.type==='progress' && message.progress===100));
      // Decode the output fully: malformed frames must fail the test.
      execFileSync('ffmpeg',['-v','error','-xerror','-i',file,'-f','null','-']);
    } finally { rmSync(join(folder,'encoded.mp3'),{force:true}); rmdirSync(folder); }
  });
}
