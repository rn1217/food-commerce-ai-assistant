from fastapi import FastAPI

#서비스의 앱 객체 생성
app = FastAPI(title="Food Commerce AI Assistant")


@app.get("/health")
def health_check(): #요청 처리할 함수 정의
    return {"status": "ok"} #응답 딕셔너리

@app.get("/hello")
def say_hello(name: str = "방문자"):
    return {"message": f"{name}님, 안녕하세요!"}