import cv2
import os
from datetime import datetime
import numpy as np

# UI méretek és elrendezés
control_panel_width = 200
window_width = 800
window_height = 480
video_area_width = window_width - control_panel_width
video_area_height = window_height

# Dropdown és Capture gomb pozíciók
dropdown_active = False
dropdown_x, dropdown_y, dropdown_w, dropdown_h = 20, 50, 160, 30
capture_button_x, capture_button_y, capture_button_w, capture_button_h = 20, 250, 160, 40

available_cams = []  # elérhető kamera indexek
current_selection = None  # jelenleg kiválasztott kamera index
cap = None  # aktuális VideoCapture objektum


def detect_cameras(max_index=5):
    cams = []
    for i in range(max_index):
        temp_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if temp_cap is not None and temp_cap.isOpened():
            ret, frame = temp_cap.read()
            if ret:
                cams.append(i)
            temp_cap.release()
    return cams


def draw_control_panel(ui_img):
    # Rajzoljuk a vezérlőpanel háttérét (bal sáv)
    cv2.rectangle(ui_img, (0, 0), (control_panel_width, window_height), (50, 50, 50), -1)

    # Dropdown felirat
    cv2.putText(ui_img, "Camera:", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    # Dropdown doboz
    cv2.rectangle(ui_img, (dropdown_x, dropdown_y), (dropdown_x + dropdown_w, dropdown_y + dropdown_h), (255, 255, 255),
                  2)
    dropdown_text = f"{current_selection}" if current_selection is not None else "Select"
    cv2.putText(ui_img, dropdown_text, (dropdown_x + 10, dropdown_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1)

    # Ha aktív a lenyíló menü, rajzoljuk az opciókat
    if dropdown_active:
        for idx, cam in enumerate(available_cams):
            option_y = dropdown_y + (idx + 1) * dropdown_h
            cv2.rectangle(ui_img, (dropdown_x, option_y), (dropdown_x + dropdown_w, option_y + dropdown_h),
                          (100, 100, 100), -1)
            cv2.putText(ui_img, f"Camera {cam}", (dropdown_x + 10, option_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 1)
            cv2.rectangle(ui_img, (dropdown_x, option_y), (dropdown_x + dropdown_w, option_y + dropdown_h),
                          (255, 255, 255), 1)

    # Capture gomb rajzolása
    cv2.rectangle(ui_img, (capture_button_x, capture_button_y),
                  (capture_button_x + capture_button_w, capture_button_y + capture_button_h), (0, 120, 0), -1)
    cv2.putText(ui_img, "Capture", (capture_button_x + 20, capture_button_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (255, 255, 255), 2)

    # Utasítások a panel alján
    cv2.putText(ui_img, "Click dropdown to change cam", (10, window_height - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 200, 200), 1)
    cv2.putText(ui_img, "Press 'q' to quit", (10, window_height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200),
                1)


def mouse_callback(event, x, y, flags, param):
    global dropdown_active, current_selection, cap
    # Csak a vezérlőpanel (bal sáv) kattintásait dolgozzuk fel
    if event == cv2.EVENT_LBUTTONDOWN:
        if x < control_panel_width:
            # Ha a kattintás a dropdown dobozra esik
            if dropdown_x <= x <= dropdown_x + dropdown_w and dropdown_y <= y <= dropdown_y + dropdown_h:
                dropdown_active = not dropdown_active
                return
            # Ha a dropdown aktív, ellenőrizzük, hogy valamelyik opcióra kattintottunk-e
            if dropdown_active:
                for idx, cam in enumerate(available_cams):
                    option_y = dropdown_y + (idx + 1) * dropdown_h
                    if dropdown_x <= x <= dropdown_x + dropdown_w and option_y <= y <= option_y + dropdown_h:
                        current_selection = cam
                        dropdown_active = False
                        if cap is not None:
                            cap.release()
                        cap = cv2.VideoCapture(cam, cv2.CAP_DSHOW)
                        print(f"Switched to camera {cam}")
                        return
            # Ha a kattintás a Capture gombon van
            if capture_button_x <= x <= capture_button_x + capture_button_w and capture_button_y <= y <= capture_button_y + capture_button_h:
                param['capture'] = True


def capture_image(frame):
    pictures_dir = "pictures"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    save_folder = os.path.join(pictures_dir, timestamp)
    os.makedirs(save_folder, exist_ok=True)
    filename = os.path.join(save_folder, f"capture_cam{current_selection}_{timestamp}.jpg")
    cv2.imwrite(filename, frame)
    print(f"Image saved: {filename}")


def main():
    global available_cams, current_selection, cap
    available_cams = detect_cameras()
    if not available_cams:
        print("No available camera found.")
        return

    current_selection = available_cams[0]
    cap = cv2.VideoCapture(current_selection, cv2.CAP_DSHOW)

    cv2.namedWindow("My_GUI", cv2.WINDOW_AUTOSIZE)
    mouse_params = {'capture': False}
    cv2.setMouseCallback("My_GUI", mouse_callback, mouse_params)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to capture frame.")
            break
        # A kamera képkockáját átméretezzük a jobb oldali videó terület méreteire
        frame_resized = cv2.resize(frame, (video_area_width, video_area_height))

        # Készítünk egy üres, teljes ablakméretű képet
        ui_img = np.zeros((window_height, window_width, 3), dtype=np.uint8)
        # A bal oldali vezérlőpanelt rajzoljuk
        control_panel_area = ui_img[0:window_height, 0:control_panel_width]
        draw_control_panel(control_panel_area)
        # A jobb oldali videó képet beillesztjük
        ui_img[0:video_area_height, control_panel_width:window_width] = frame_resized

        cv2.imshow("My_GUI", ui_img)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

        if mouse_params.get('capture', False):
            capture_image(frame)
            mouse_params['capture'] = False

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
