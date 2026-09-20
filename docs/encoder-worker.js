/* Encoder is isolated in a worker so the page stays responsive. */
importScripts('./vendor/lame.min.js');
self.onmessage = ({data}) => {
  try {
    const {channels, sampleRate, bitrate, mono} = data;
    const count = mono ? 1 : Math.min(2, channels.length);
    const encoder = new lamejs.Mp3Encoder(count, sampleRate, bitrate);
    const length = channels[0].length;
    const chunks = [];
    let lastProgress = -1;
    const pcm = (value) => {
      const clamped = Math.max(-1, Math.min(1, value));
      return Math.round(clamped * (clamped < 0 ? 32768 : 32767));
    };
    for (let offset = 0; offset < length; offset += 1152) {
      const size = Math.min(1152, length - offset);
      const left = new Int16Array(size);
      const right = count === 2 ? new Int16Array(size) : null;
      for (let i = 0; i < size; i++) {
        let value = channels[0][offset + i];
        if (mono && channels.length > 1) value = (value + channels[1][offset + i]) / 2;
        left[i] = pcm(value);
        if (right) right[i] = pcm(channels[1][offset + i]);
      }
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
