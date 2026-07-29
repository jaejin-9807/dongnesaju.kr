# 동네사주카페 — Railway 배포 가이드 (dongnesaju.kr 연결)

이 폴더에는 배포용 Dockerfile, .dockerignore, railway.json 이 포함되어 있습니다.
아래 순서대로만 하면 https://www.dongnesaju.kr 로 서비스가 열립니다.

## STEP 1. 코드를 GitHub에 올리기
1. github.com 가입 → New repository (예: dongnesaju) 생성 (Private 권장)
2. 내 컴퓨터의 payment-server 폴더 안 내용을 그 저장소에 올립니다.
   - GitHub Desktop 프로그램을 쓰면 클릭만으로 올릴 수 있어요.
   - ⚠️ .env 파일은 올리지 마세요(비밀번호 포함).

## STEP 2. Railway에서 프로젝트 만들기
1. railway.app 가입(GitHub 계정으로 로그인)
2. New Project → Deploy from GitHub repo → 방금 만든 저장소 선택
3. Railway가 Dockerfile을 자동 감지해서 빌드 시작 (5~10분, Chromium 설치 포함)

## STEP 3. 환경변수(Variables) 입력  (.env 대신 여기에)
- ADMIN_ID = rlawowls2000
- ADMIN_PASSWORD = (원하는 비밀번호)
- SESSION_SECRET = (아무 긴 임의 문자열)
- BASE_URL = https://www.dongnesaju.kr
- DATA_DIR = /data
- PYTHON_BIN = python3
- ANTHROPIC_API_KEY = (있으면 입력)
- MAIL_HOST/MAIL_PORT/MAIL_USER/MAIL_PASS/NOTIFY_EMAIL = (이메일 발송용)
- TOSS_CLIENT_KEY/TOSS_SECRET_KEY = (토스 키)
- (카카오/네이버/구글/페이 키는 발급되면 입력)
- ※ PORT 는 Railway가 자동 주입하니 넣지 마세요.

## STEP 4. 데이터 영구 저장 (Volume) — 중요
재배포 때 주문·회원·PDF가 사라지지 않게 볼륨 연결:
1. 서비스 → Settings → Volumes → New Volume
2. Mount path 를 /data 로 지정 → 저장
   (코드가 DATA_DIR=/data 를 읽어 orders.json/users.json/generated_pdfs 를 여기 저장)

## STEP 5. 접속 주소 만들기 + 테스트
1. 서비스 → Settings → Networking → Generate Domain
2. xxxx.up.railway.app 주소로 사이트가 뜨는지 확인
3. /admin-login.html 관리자 로그인, 0원 이벤트 주문/PDF 생성 테스트

## STEP 6. 내 도메인(dongnesaju.kr) 연결
1. 서비스 → Settings → Networking → Custom Domain → Add → www.dongnesaju.kr 입력
2. Railway가 CNAME 대상 주소(예: xxxx.up.railway.app)를 알려줍니다.
3. 가비아 DNS 관리:
   - 기존 A 레코드(집 IP 112.148.62.150)는 삭제
   - 타입 CNAME, 호스트 www, 값/위치 = Railway가 준 주소
   - 루트(@)는 CNAME 불가 → 가비아 웹 포워딩으로 dongnesaju.kr → https://www.dongnesaju.kr 리다이렉트(선택)
4. 몇 분~몇 시간 뒤 https://www.dongnesaju.kr 접속 (HTTPS 자동)

## STEP 7. 마무리
- BASE_URL 이 https://www.dongnesaju.kr 인지 확인
- 소셜 로그인 콜백 URL, 결제 returnUrl 을 새 도메인으로 각 콘솔에 등록

## 참고
- Railway는 사용량 기반 요금. Chromium 때문에 메모리 1GB 정도 사용.
- 빌드 실패 시 Deployments 로그의 빨간 에러 줄 확인.
