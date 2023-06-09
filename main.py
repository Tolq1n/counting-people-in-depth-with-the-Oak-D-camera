#!/usr/bin/env python3
import argparse
import cv2
import depthai as dai
import numpy as np
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from socketserver import ThreadingMixIn
from time import sleep
import depthai as dai
import numpy as np
import cv2
import argparse
import blobconverter

import socket
def get_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(('10.254.254.254', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
            print(f"Serving at: {IP}:8000")
        return IP

DETECTION_ROI = (200, 100, 900, 500)
#(200,100,1000,700) # Specific to `depth-person-counting-01` recording

class TextHelper:
    def __init__(self) -> None:
        self.bg_color = (0, 0, 0)
        self.color = (255, 255, 255)
        self.text_type = cv2.FONT_HERSHEY_SIMPLEX
        self.line_type = cv2.LINE_AA
    def putText(self, frame, text, coords):
        cv2.putText(frame, text, coords, self.text_type, 1.3, self.bg_color, 5, self.line_type)
        cv2.putText(frame, text, coords, self.text_type, 1.3, self.color, 2, self.line_type)
        return frame
    def rectangle(self, frame, topLeft,bottomRight, size=1.):
        cv2.rectangle(frame, topLeft, bottomRight, self.bg_color, int(size*4))
        cv2.rectangle(frame, topLeft, bottomRight, self.color, int(size))
        
        return frame
    
HTTP_SERVER_PORT = 8000

                
# HTTPServer MJPEG
class VideoStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--jpgboundary')
        self.end_headers()
        while True:
            sleep(0.1)
            if hasattr(self.server, 'frametosend'):
                ok, encoded = cv2.imencode('.jpg', self.server.frametosend)
                self.wfile.write("--jpgboundary".encode())
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('Content-length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                self.end_headers()
   
             
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass

# start MJPEG HTTP Server
server_HTTP = ThreadedHTTPServer((get_ip(), HTTP_SERVER_PORT), VideoStreamHandler)
print("Starting MJPEG HTTP Server...")
th2 = threading.Thread(target=server_HTTP.serve_forever)
th2.daemon = True
th2.start()

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--path', default='depth-people-counting-01', type=str, help="Path to depthai-recording")
args = parser.parse_args()

def to_planar(arr: np.ndarray) -> list:
    return arr.transpose(2, 0, 1).flatten()

THRESH_DIST_DELTA = 0.5
THRESH_DIST_DELTAY = 0.2

class PeopleCounter:
    def __init__(self):
        self.tracking = {}
        self.lost_cnt = {}
        self.people_counter = [0,0,0,0] # Up, Down, Left, Right
        self.total = 0
        self.score = 0

    def __str__(self) -> str:
        
        return f"Left: {self.people_counter[2]}, Right: {self.people_counter[3]}, Up: {self.people_counter[0]}, Down: {self.people_counter[1]}"

    def tracklet_removed(self, coords1, coords2):
        deltaX = coords2[0] - coords1[0]
        print('deltaX', deltaX)
        deltaY = coords2[1] - coords1[1]
        print('deltaY', deltaY)

        if THRESH_DIST_DELTA < abs(deltaX):
            self.people_counter[2 if 0 > deltaX else 3] += 1
            print(f"Left: {self.people_counter[2]}, Right: {self.people_counter[3]}, Up: {self.people_counter[0]}, Down: {self.people_counter[1]}")
            

        if abs(deltaY) > abs(deltaX) and abs(deltaY) > THRESH_DIST_DELTAY:
            self.people_counter[0 if 0 > deltaY else 1] += 1
            print(f"Left: {self.people_counter[2]}, Right: {self.people_counter[3]}, Up: {self.people_counter[0]}, Down: {self.people_counter[1]}")

        #DETECTION_ROI = (200, 100, 900, 500)

        
        
    
    def get_centroid(self, roi):
        x1 = roi.topLeft().x
        y1 = roi.topLeft().y
        x2 = roi.bottomRight().x
        y2 = roi.bottomRight().y
        # print((x2+x1)/2, (y2+y1)/2)
        return ((x2+x1)/2, (y2+y1)/2)

    def new_tracklets(self, tracklets):
        for tracklet in tracklets:
            # If new tracklet, save its centroid
            if tracklet.status == dai.Tracklet.TrackingStatus.NEW:
                self.tracking[str(tracklet.id)] = self.get_centroid(tracklet.roi)
                self.lost_cnt[str(tracklet.id)] = 0
            elif tracklet.status == dai.Tracklet.TrackingStatus.TRACKED:
                self.lost_cnt[str(tracklet.id)] = 0
            elif tracklet.status == dai.Tracklet.TrackingStatus.LOST:
                self.lost_cnt[str(tracklet.id)] += 1
                # Tracklet has been lost for too long
                if 10 < self.lost_cnt[str(tracklet.id)]:
                    self.lost_cnt[str(tracklet.id)] = -999
                    self.tracklet_removed(self.tracking[str(tracklet.id)], self.get_centroid(tracklet.roi))
            elif tracklet.status == dai.Tracklet.TrackingStatus.REMOVED:
                if 0 <= self.lost_cnt[str(tracklet.id)]:
                    self.lost_cnt[str(tracklet.id)] = -999
                    self.tracklet_removed(self.tracking[str(tracklet.id)], self.get_centroid(tracklet.roi))

pipeline = dai.Pipeline()


objectTracker = pipeline.createObjectTracker()
objectTracker.inputTrackerFrame.setBlocking(True)
objectTracker.inputDetectionFrame.setBlocking(True)
objectTracker.inputDetections.setBlocking(True)
objectTracker.setDetectionLabelsToTrack([1])  # track only person
# possible tracking types: ZERO_TERM_COLOR_HISTOGRAM, ZERO_TERM_IMAGELESS
objectTracker.setTrackerType(dai.TrackerType.ZERO_TERM_COLOR_HISTOGRAM)
# take the smallest ID when new object is tracked, possible options: SMALLEST_ID, UNIQUE_ID
objectTracker.setTrackerIdAssignmentPolicy(dai.TrackerIdAssignmentPolicy.UNIQUE_ID)

xinFrame = pipeline.createXLinkIn()
xinFrame.setStreamName("frameIn")
xinFrame.out.link(objectTracker.inputDetectionFrame)

# Maybe we need to send the old frame here, not sure
xinFrame.out.link(objectTracker.inputTrackerFrame)

xinDet = pipeline.createXLinkIn()
xinDet.setStreamName("detIn")
xinDet.out.link(objectTracker.inputDetections)

trackletsOut = pipeline.createXLinkOut()
trackletsOut.setStreamName("trackletsOut")
objectTracker.out.link(trackletsOut.input)

leftCam = pipeline.createMonoCamera()
leftCam.setBoardSocket(dai.CameraBoardSocket.LEFT)
leftCam.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)

rightCam = pipeline.createMonoCamera()
rightCam.setBoardSocket(dai.CameraBoardSocket.RIGHT)
rightCam.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)

#create stereo node
stereo = pipeline.createStereoDepth()
stereo.initialConfig.setConfidenceThreshold(200)

stereo.initialConfig.setMedianFilter(dai.StereoDepthProperties.MedianFilter.KERNEL_7x7) # KERNEL_7x7 default
stereo.setLeftRightCheck(True)
#nodes.stereo.setSubpixel(True)

# stereo.initialConfig.setMedianFilter(dai.StereoDepthProperties.MedianFilter.KERNEL_7x7) # KERNEL_7x7 default
# stereo.setLeftRightCheck(True)
# # nodes.stereo.setSubpixel(True)

depthOut = pipeline.createXLinkOut()
depthOut.setStreamName("depthOut")
stereo.disparity.link(depthOut.input)

leftCam.out.link(stereo.left)
rightCam.out.link(stereo.right)

with dai.Device(pipeline) as device:

    depthQ = device.getOutputQueue(name="depthOut", maxSize=4, blocking=False)
    trackletsQ = device.getOutputQueue(name="trackletsOut", maxSize=4, blocking=False)

    detInQ = device.getInputQueue("detIn")
    frameInQ = device.getInputQueue("frameIn")

    disparityMultiplier = 255 / stereo.initialConfig.getMaxDisparity()

    text = TextHelper()
    counter = PeopleCounter()

    while True:
        depthFrame = depthQ.get().getFrame()
        depthFrame = (depthFrame*disparityMultiplier).astype(np.uint8)
        depthRgb = cv2.applyColorMap(depthFrame, cv2.COLORMAP_JET)

        trackletsIn = trackletsQ.tryGet()
        if trackletsIn is not None:
            counter.new_tracklets(trackletsIn.tracklets)



        # Crop only the corridor:
        
        cropped = depthFrame[DETECTION_ROI[1]:DETECTION_ROI[3], DETECTION_ROI[0]:DETECTION_ROI[2]]
        #cv2.imshow('Crop', cropped)

        ret, thresh = cv2.threshold(cropped, 125, 145, cv2.THRESH_BINARY)

        blob = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (37,37)))
        # cv2.imshow('blob', blob)

        edged = cv2.Canny(blob, 20, 80)
        # cv2.imshow('Canny', edged)

        contours, hierarchy = cv2.findContours(edged,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)

        dets = dai.ImgDetections()
        if len(contours) != 0:
            c = max(contours, key = cv2.contourArea)
            x,y,w,h = cv2.boundingRect(c)
            cv2.imshow('Rect', text.rectangle(blob, (x,y), (x+w, y+h)))
            x += DETECTION_ROI[0]
            y += DETECTION_ROI[1]
            area = w*h

            if 15000 < area:
                #Send the detection to the device - ObjectTracker node
                det = dai.ImgDetection()
                det.label = 1
                det.confidence=1.0
                det.xmin = x
                det.ymin = y
                det.xmax = x + w
                det.ymax = y + h
                dets.detections = [det]

               # Draw rectangle on the biggest countour
                text.rectangle(depthRgb, (x, y), (x+w, y+h), size=2)

        detInQ.send(dets)
        imgFrame = dai.ImgFrame()
        imgFrame.setData(to_planar(depthRgb))
        imgFrame.setType(dai.RawImgFrame.Type.BGR888p)
        imgFrame.setWidth(depthRgb.shape[0])
        imgFrame.setHeight(depthRgb.shape[1])
        frameInQ.send(imgFrame)

        text.rectangle(depthRgb, (DETECTION_ROI[0], DETECTION_ROI[1]), (DETECTION_ROI[2], DETECTION_ROI[3]))
        text.putText(depthRgb, str(counter), (20, 40))

        cv2.imshow('depthX', depthRgb)
        server_HTTP.frametosend = depthRgb
            
     
        if cv2.waitKey(1) == ord('q'):
            
            break
        
    print('Closing oak-d.')