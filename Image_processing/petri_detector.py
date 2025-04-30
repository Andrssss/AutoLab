import cv2
import numpy as np


# PetriDetector get a picture tries to the edges of the Petri and returns a mask. If cant find than returns "None"
class PetriDetector:
    def __init__(self):
        self.blur = 7 #gauss for noise reduction and edge smooting
        self.sensitivity = 30 # controls how strictly the algorithm decides whether a set of edge points forms a valid circle. Its for cv2.HoughCircles
        self.min_radius = 50  # reduced for wider search
        self.max_radius = 300  # increased for larger Petri dishes
        self.center_tolerance = 0.4  # more tolerant of off-center dishes

    def set_params(self, blur, sensitivity):
        self.blur = blur
        self.sensitivity = sensitivity

    def detect(self, image):
        if image is None:
            return None

        # it needed for cv2.HoughCircles, it works only in one channel
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.blur, self.blur), 0)

        h, w = gray.shape[:2] # height, width
        img_center = (w // 2, h // 2) # circles middle point to calculate how far is the detected circles

        # biult in circle finder algorithm, it can find more than 1
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=100,
                                   param1=50, param2=self.sensitivity,
                                   minRadius=self.min_radius, maxRadius=self.max_radius)

        mask = None


        if circles is not None:
            circles = np.uint16(np.around(circles)) # need to round values and now we can index with them
            valid_circle_found = False
            for i in circles[0]:
                x, y, r = int(i[0]), int(i[1]), int(i[2]) # x,y cicrle middle point, and r is the radius
                # the difference between the middle point, and cicle middle point
                dx = abs(x - img_center[0]) / w
                dy = abs(y - img_center[1]) / h

                if dx > self.center_tolerance or dy > self.center_tolerance:
                    continue

                margin = r // 2
                x1, x2 = max(0, x - margin), min(w, x + margin)
                y1, y2 = max(0, y - margin), min(h, y + margin)
                roi = gray[y1:y2, x1:x2] # ROI (Region of Interest), it works from the gray picture

                if roi.size == 0:
                    continue

                mean_brightness = np.mean(roi)
                std_brightness = np.std(roi)

                # Loosen brightness condition to allow grid lines and markings
                if mean_brightness < 50:
                    continue

                if std_brightness > 60:
                    continue

                mask = np.zeros(gray.shape, dtype=np.uint8) #cv2 empty black picture, same size as gray
                cv2.circle(mask, (x, y), r, 255, -1) # it draws a cicle in the mask. And fill it.
                #   circle(picture, middle_point, radius, colour, fill_it?! )
                # print(f"[OK] Petri kör elfogadva: ({x}, {y}), r={r}")
                valid_circle_found = True
                break

            if not valid_circle_found:
                print("[INFO] Kör talált, de egyik sem felelt meg a szűrésnek.")
        else:
            print("[INFO] Nem találtunk kört.")


        # Save the mask as an image for debugging
        # cv2.imwrite("petri_mask_output.png", mask)
        # print("[INFO] Mask saved as petri_mask_output.png")

        return mask
