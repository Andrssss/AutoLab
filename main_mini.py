import cv2

if __name__ == "__main__":
    vavailable = []

    # Próbáljunk 5 lehetséges kameraindexet
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(i)
            cap.release()

