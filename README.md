# MP3 용량 줄이기

MP3 파일 여러 개를 **48kbps**로 압축하는 한국어 웹사이트와 Windows 프로그램입니다. 웹 버전은 브라우저 안에서 처리하며, 오디오 파일을 서버로 전송하지 않습니다.

> 48kbps는 비트레이트입니다. 파일 전체 용량을 48KB로 맞추는 기능은 아닙니다. 48kbps에서 1분은 약 360KB, 10분은 약 3.6MB입니다. 파일 헤더에 따라 실제 크기는 조금 달라집니다.

## 웹사이트 사용

`docs/` 폴더에 설치 없이 사용하는 웹 버전이 있습니다.

1. **MP3 파일 선택** 또는 끌어놓기로 파일을 추가합니다.
2. 기본 **48kbps / 모노** 설정으로 **압축 시작**을 누릅니다.
3. 파일별 **다운로드**를 눌러 압축 파일을 저장합니다.

여러 파일, 진행률, 취소, 오류 후 재시도, 중복 파일명 방지, 원본이 더 작을 때 저장 생략을 지원합니다. 음질과 채널 설정은 아직 완료하지 않은 파일에 적용됩니다. 완료한 파일을 다른 설정으로 다시 압축하려면 목록에서 제거한 뒤 다시 추가하세요.

파일당 최대 **50MB / 30분**, 출력 샘플레이트 **24kHz**입니다. 브라우저 메모리를 사용하므로 긴 파일은 PC에서 사용하는 것이 좋습니다. 새로고침하거나 탭을 닫으면 목록과 결과가 사라집니다. 스테레오를 선택해도 원본이 모노이면 모노를 유지합니다.

### 로컬 웹 실행

```powershell
python -m http.server 5173 --bind 127.0.0.1 --directory docs
```

브라우저에서 `http://127.0.0.1:5173`을 엽니다. HTML 파일을 직접 두 번 클릭하면 브라우저 보안 제한으로 압축기가 작동하지 않을 수 있습니다.

### 웹 배포

정적 파일만으로 작동하므로 `docs/` 폴더를 정적 호스팅에 배포하면 됩니다. GitHub Pages에서는 **Settings → Pages → Deploy from a branch → main / docs**를 선택합니다. GitHub Free 계정은 저장소가 공개되어야 Pages를 사용할 수 있습니다. 비공개 저장소는 자동으로 공개하지 않습니다.

오디오 디코딩은 Web Audio API, MP3 인코딩은 별도 Worker의 [lamejs 1.2.1](https://github.com/zhuker/lamejs)을 사용합니다. 라이브러리를 자체 호스팅하므로 외부 CDN을 호출하지 않습니다. 라이선스와 원본 소스 패키지는 `docs/vendor/`에 포함되어 있습니다.

## Windows 프로그램 사용

1. Python 3.10 이상과 [FFmpeg](https://ffmpeg.org/download.html)를 설치합니다. FFmpeg에는 `libmp3lame` 인코더가 필요합니다.
2. `ffmpeg`를 PATH에 등록하거나 `ffmpeg.exe`를 `app.py`와 같은 폴더에 둡니다.
3. Windows에서는 `실행.bat`를 두 번 클릭합니다. 또는 `python app.py`를 실행합니다.
4. **파일 추가**로 MP3를 선택하고 저장 폴더를 정한 뒤 **압축 시작**을 누릅니다.

Python을 포함한 Windows 실행 파일도 빌드할 수 있습니다. 실행 파일에는 FFmpeg가 포함되지 않으며, `ffmpeg.exe`를 실행 파일 옆에 두거나 PATH에 등록해야 합니다.

## 동작

- 기본 설정: **48kbps / 모노 / 24kHz**. 32·64·96·128kbps 및 스테레오 선택도 지원합니다.
- 원본은 보존하고 `파일명_48kbps.mp3`로 저장합니다. 같은 이름이 있으면 번호를 붙입니다.
- 기본 저장 위치는 첫 번째 원본 파일 옆의 `compressed` 폴더입니다.
- 변환 후 원본보다 크거나 같으면 저장을 생략합니다.
- 앨범 사진, 메타데이터 태그, 챕터는 제거합니다.
- 파일별 결과, 전체 진행, 절약한 크기를 표시합니다. 오류가 난 파일은 건너뛰고 다음 파일을 처리합니다.
- 취소하면 현재 변환의 임시 파일을 정리합니다. 앞서 완료한 파일은 유지합니다.
- 같은 이름의 파일을 서로 다른 폴더에서 추가해도 각각 저장됩니다.

낮은 비트레이트로 다시 압축하면 음질이 떨어집니다. 기본 모노 설정은 음성 녹음에 적합합니다. 음악에는 스테레오와 더 높은 비트레이트를 고려하세요. 재변환할 때는 원본을 선택하는 것이 좋습니다.

## 명령줄 사용

```powershell
python compressor.py "녹음.mp3" -o "압축결과"
python compressor.py "첫째.mp3" "둘째.mp3" -b 48 --stereo -o "압축결과"
```

오류가 발생한 파일이 있으면 종료 코드 1을 반환합니다. 원본이 더 작아서 저장을 생략한 경우는 정상 처리입니다.

## 확인 및 Windows 실행 파일 만들기

```powershell
python -m unittest discover -s tests -v
node --test tests/test_web_encoder.cjs
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name MP3-Compressor app.py
```

결과는 `dist/MP3-Compressor.exe`입니다. FFmpeg·ffprobe가 설치되어 있어야 실제 MP3 변환 테스트가 실행됩니다. GUI는 Python의 기본 Tkinter를 사용합니다. 일부 Linux 배포판에서는 별도 `python3-tk` 패키지가 필요합니다.

GitHub Actions는 실제 MP3 변환을 검사하고 Windows 실행 파일을 빌드해 작업 결과물로 보관합니다. FFmpeg는 저장소나 실행 파일에 포함하지 않습니다.
