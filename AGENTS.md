# RS 프로젝트

한국 주식시장(KOSPI, KOSDAQ, KRX)의 상대강도(RS) 지표를 계산하는 프로젝트.

## 작업 규칙

- **main 브랜치에 직접 push 금지.** 모든 변경은 별도 브랜치에서 PR을 통해 진행한다.
- 기능 제안 시 사용자의 명시적 확인 없이 구현하지 않는다. (`verify-before-build.md` 참고)

## 개발 환경

- Python: `uv run`으로 실행 (의존성 관리는 uv)
- Jekyll: rbenv Ruby 3.3.10, `bundle exec jekyll serve --limit_posts 5 --future`
- GitHub Pages: `baseurl: /rs` (`_config.yml`)

## 제품 요구사항

`PRD.md` 참고.
