import streamlit as st
from PIL import Image
import os
from datetime import datetime

# 1. 저장할 폴더 만들기 (없으면 자동 생성)
SAVE_FOLDER = "collected_images"
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)

# 2. 웹 앱 제목
st.title("Turfgrass Data Collector 🌱")
st.write("핸드폰으로 사진을 찍으면 서버(컴퓨터)에 자동 저장됩니다.")

# 3. 카메라 위젯 실행
# 모바일에서는 자동으로 카메라가 켜지고, PC에서는 웹캠이 켜집니다.
img_file = st.camera_input("Take a picture")

# 4. 사진이 찍히면 저장 로직 실행
if img_file is not None:
    # 이미지 파일 열기
    image = Image.open(img_file)
    
    # 파일명 생성 (중복 방지를 위해 현재 시간 사용)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"turf_{timestamp}.jpg"
    save_path = os.path.join(SAVE_FOLDER, filename)
    
    # 저장
    image.save(save_path)
    
    # 화면에 성공 메시지와 저장된 사진 정보 표시
    st.success(f"저장 완료! 파일명: {filename}")
    st.write(f"이미지 크기: {image.size}") # 해상도 확인용