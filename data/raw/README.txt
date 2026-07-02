원본 대형 지명 파일을 여기에 넣습니다 (선택 사항).

저장소에는 이미 미리 계산된 경량 풀(../region_pools.json, ../location_pools.json)이
포함돼 있어, 이 폴더가 비어 있어도 파이프라인은 정상 실행됩니다.

풀을 원본에서 다시 만들고 싶을 때만, 아래 두 파일을 (파일명 그대로) 이 폴더에 넣고
프로젝트 루트에서  python tools/build_pools.py  를 실행하세요.

  지역별_지명_지역_도로명주소_통합_work.csv   (약 118MB)
  location.json                                (약 294MB)

두 파일은 용량이 커서 저장소에는 포함하지 않습니다(.gitignore 처리).
