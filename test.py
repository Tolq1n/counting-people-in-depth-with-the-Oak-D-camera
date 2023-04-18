# import cv2
# import depthai as dai

# pipeline = dai.Pipeline()

# camRgb = pipeline.createColorCamera()

# xoutRgb = pipeline.createXLinkOut()
# xoutRgb.setStreamName("rgb")
# camRgb.preview.link(xoutRgb.input)

# device_info = dai.DeviceInfo("192.168.0.100")
# # device_info = depthai.DeviceInfo("14442C108144F1D000") # MXID
# # device_info = depthai.DeviceInfo("3.3.3") # USB port name

# with dai.Device(pipeline, device_info) as device:
#     qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
#     while True:
#         cv2.imshow("rgb", qRgb.get().getCvFrame())
#         if cv2.waitKey(1) == ord('q'):
#             break