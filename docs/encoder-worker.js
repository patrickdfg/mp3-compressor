/* Encoder is isolated in a worker so the page stays responsive. */
importScripts('./vendor/lame.min.js');
self.onmessage = ({data}) => {
  try {
    // channels는 이미 16비트이고 모노 합치기도 끝난 상태로 넘어온다.
    const {channels, sampleRate, bitrate} = data;
    const count = Math.min(2, channels.length);
    const encoder = new lamejs.Mp3Encoder(count, sampleRate, bitrate);
    const length = channels[0].length;
    const chunks = [];
    let lastProgress = -1;
    for (let offset = 0; offset < length; offset += 1152) {
      const size = Math.min(1152, length - offset);
      const left = channels[0].subarray(offset, offset + size);
      const right = count === 2 ? channels[1].subarray(offset, offset + size) : null;
      const chunk = right ? encoder.encodeBuffer(left, right) : encoder.encodeBuffer(left);
      if (chunk.length) chunks.push(new Uint8Array(chunk));
      const progress = Math.floor((offset + size) / length * 100);
      if (progress >= lastProgress + 2 || progress === 100) {
        self.postMessage({type:'progress', progress});
        lastProgress = progress;
      }
    }
    const tail = encoder.flush();
    if (tail.length) chunks.push(new Uint8Array(tail));
    self.postMessage({type:'done', blob:new Blob(chunks, {type:'audio/mpeg'})});
  } catch (error) {
    self.postMessage({type:'error', message:error.message || '압축에 실패했습니다.'});
  }
};
