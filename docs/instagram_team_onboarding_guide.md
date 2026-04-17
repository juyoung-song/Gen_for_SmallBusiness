# Instagram OAuth 팀원 가이드

이 문서는 `mobile_app.py + Stitch PWA` 기준으로 팀원이 Instagram OAuth 연결을 테스트하기 위한 가이드다.

## 1. Meta 앱 개발 모드 전제

현재 Meta 앱이 개발 모드라면 테스트 가능한 Facebook 계정은 앱 역할에 등록된 계정뿐이다.

팀원이 Meta 앱 소유자에게 전달할 정보:

```text
Meta 앱 개발 모드 테스트 권한 요청드립니다.

제 Facebook 로그인 이메일을 앱 역할에 Tester 또는 Developer로 초대해주세요.
초대 후 제가 https://developers.facebook.com/requests/ 에서 수락하겠습니다.

테스트할 Instagram 계정은 professional account여야 하고,
해당 Instagram 계정이 Facebook Page에 연결되어 있어야 합니다.
또한 제가 로그인하는 Facebook 계정이 그 Page에 접근 권한을 가지고 있어야 합니다.
```

## 2. Instagram 계정 조건

OAuth 연결 후보에 잡히려면 아래 조건이 모두 필요하다.

- Instagram 계정이 Professional 계정이어야 한다.
- Instagram 계정이 Facebook Page에 연결되어 있어야 한다.
- Meta 로그인에 쓰는 Facebook 계정이 해당 Page 권한을 가지고 있어야 한다.
- 앱이 개발 모드라면 그 Facebook 계정이 앱 Role에 등록되어 있어야 한다.
- Meta 앱에 필요한 권한 흐름이 열려 있어야 한다.

현재 요청 scope:

```text
instagram_basic
instagram_content_publish
pages_show_list
pages_read_engagement
```

## 3. Redirect URI

모바일 PWA 운영 callback:

```text
https://brewgram.duckdns.org/api/mobile/instagram/callback
```

Streamlit legacy 테스트를 계속 쓸 경우:

```text
http://localhost:8501/
```

Meta 개발자 센터의 `Valid OAuth Redirect URIs`에는 위 URI를 정확히 등록한다. 루트 도메인 `https://brewgram.duckdns.org/`만 등록하면 모바일 callback과 일치하지 않는다.

## 4. VM env

VM의 `/etc/brewgram/mobile_app.env`에 아래 값이 필요하다.

```env
META_APP_ID=...
META_APP_SECRET=...
TOKEN_ENCRYPTION_KEY=...
META_REDIRECT_URI_MOBILE=https://brewgram.duckdns.org/api/mobile/instagram/callback
```

`TOKEN_ENCRYPTION_KEY`는 Fernet 키여야 하며, 한 번 OAuth 연결에 사용한 뒤에는 바꾸면 기존 암호화 토큰을 복호화할 수 없다.

## 5. 연결 테스트 절차

1. 모바일 또는 브라우저에서 `https://brewgram.duckdns.org`에 접속한다.
2. 온보딩을 완료한다.
3. 설정 또는 Instagram 연결 화면에서 `Meta로 연결하기`를 누른다.
4. Meta 로그인 화면에서 테스트 계정으로 로그인한다.
5. 연결할 Facebook Page와 Instagram professional account 권한을 승인한다.
6. 후보가 여러 개면 원하는 계정을 선택한다.
7. 후보가 자동으로 잡히지 않으면 UI에서 Instagram `@username`을 입력한다.

## 6. @username 수동 연결 기준

수동 입력은 아무 Instagram 계정이나 임의로 연결하는 기능이 아니다.

`@username`은 현재 Meta 로그인 계정이 접근 가능한 Facebook Page 후보 목록 안에서만 매칭된다. 후보 목록에 없는 계정이면 연결되지 않는다.

후보에 없을 때 확인할 것:

- 해당 Instagram 계정이 Facebook Page에 연결되어 있는지
- 현재 Facebook 계정이 그 Page 권한을 가지고 있는지
- 앱 개발 모드에서 현재 Facebook 계정이 Tester/Developer/Admin인지
- OAuth 승인 화면에서 Page 권한을 누락하지 않았는지

## 7. 업로드 정책

모바일 업로드는 기본적으로 OAuth로 연결된 계정만 사용한다.

- `.env`의 `META_ACCESS_TOKEN` / `INSTAGRAM_ACCOUNT_ID` fallback은 기본적으로 모바일 업로드에서 사용하지 않는다.
- 내부 데모에서 VM 고정 업로드 계정을 쓰려면 `ALLOW_DEFAULT_INSTAGRAM_UPLOAD=true`, `META_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`를 함께 설정한다.
- 연결된 계정이 없으면 업로드 API는 계정 연결이 필요하다는 메시지를 반환한다.
- 업로드 성공 시 응답의 `account_username`이 실제 게시 대상 계정이다.
