# Import packages
import os
import cv2
import numpy as np
import sys
import time
from threading import Thread
import importlib.util
# Import TensorFlow libraries
# tflite_runtime is installed, import interpreter from tflite_runtime
from tflite_runtime.interpreter import Interpreter
from VideoStream import *

class ODV:
    INPUT_MEAN = 127.5
    INPUT_STD = 127.5
   
    def __init__(self, MODEL_NAME, GRAPH_NAME, LABELMAP_NAME, min_conf_threshold, resW, resH):
        # Get path to current working directory
        CWD_PATH = os.getcwd()

        # Path to .tflite file, which contains the model that is used for object detection
        PATH_TO_CKPT = os.path.join(CWD_PATH,MODEL_NAME,GRAPH_NAME)

        # Path to label map file
        PATH_TO_LABELS = os.path.join(CWD_PATH,MODEL_NAME,LABELMAP_NAME)

        # Load the label map
        with open(PATH_TO_LABELS, 'r') as f:
            self.labels = [line.strip() for line in f.readlines()]

        # Have to do a weird fix for label map if using the COCO "starter model" from
        # https://www.tensorflow.org/lite/models/object_detection/overview
        # First label is '???', which has to be removed.

        # TODO: go thorugh all labels and remove ???
        if self.labels[0] == '???':
            del(self.labels[0])
        
        self.min_threshold = min_conf_threshold
        self.imW, self.imH = int(resW), int(resH)

         # Load the Tensorflow Lite model.
        self.interpreter = Interpreter(model_path=PATH_TO_CKPT)
        self.interpreter.allocate_tensors()

        # Get model details    
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.height = self.input_details[0]['shape'][1]
        self.width = self.input_details[0]['shape'][2]
        self.floating_model = (self.input_details[0]['dtype'] == np.float32)

        # Check output layer name to determine if this model was created with TF2 or TF1,
        # because outputs are ordered differently for TF2 and TF1 models
        outname = self.output_details[0]['name']

        # We use TF1 model now, revisit
        if ('StatefulPartitionedCall' in outname): # This is a TF2 model
            self.boxes_idx, self.classes_idx, self.scores_idx = 1, 3, 0
        else: # This is a TF1 model
            self.boxes_idx, self.classes_idx, self.scores_idx = 0, 1, 2

            
        # Initialize frame rate calculation
        self.frame_rate_calc = 1
        self.freq = cv2.getTickFrequency()

        # Initialize video stream
        self.videostream = VideoStream(resolution=(self.imW, self.imH), framerate=30).start()
        time.sleep(1)

        #TODO: load image reference wid

th    def run_detection(self, focal_keyboard):  
        while True:
            # Start timer (for calculating frame rate)
            t1 = cv2.getTickCount()

            # Grab frame from video stream
            frame1 = self.videostream.read()
            frame = frame1.copy()
            boxes, classes, scores = self.detect_from_frame(frame)

            # Loop over all detections and draw detection box if confidence is above minimum threshold
            for i in range(len(scores)):
                if ((scores[i] > self.min_threshold) and (scores[i] <= 1.0)):

                    # Get bounding box coordinates and draw box
                    # Interpreter can return coordinates that are outside of image dimensions, need to force them to be within image using max() and min()
                    ymin = int(max(1,(boxes[i][0] * self.imH)))
                    xmin = int(max(1,(boxes[i][1] * self.imW)))
                    ymax = int(min(self.imH,(boxes[i][2] * self.imH)))
                    xmax = int(min(self.imW,(boxes[i][3] * self.imW)))
                    
                    # Draw object big surrounding rectangle
                    cv2.rectangle(frame, (xmin,ymin), (xmax,ymax), (10, 255, 0), 2)

                    #TODO: update
                    distance = self.distance_finder(focal_keyboard, 44, xmax-xmin)

                    # Draw label
                    object_name = self.labels[int(classes[i])] # Look up object name from "labels" array using class index
                    if (object_name != 'keyboard'):
                        distance = 0
                    label = '%s: %d%% dist: %d' % (object_name, int(scores[i]*100), distance) # Example: 'person: 72%'
                    labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2) # Get font size
                    label_ymin = max(ymin, labelSize[1] + 10) # Make sure not to draw label too close to top of window
                    cv2.rectangle(frame, (xmin, label_ymin-labelSize[1]-10), (xmin+labelSize[0], label_ymin+baseLine-10), (255, 255, 255), cv2.FILLED) 
                    # Draw white box to put label text in
                    cv2.putText(frame, label, (xmin, label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2) # Draw label text

            # Draw framerate in corner of frame
            cv2.putText(frame,'FPS: {0:.2f}'.format(self.frame_rate_calc),(30,50),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,0),2,cv2.LINE_AA)

            # All the results have been drawn on the frame, so it's time to display it.
            cv2.imshow('Object detector', frame)

            # Calculate framerate
            t2 = cv2.getTickCount()
            time1 = (t2-t1)/self.freq
            self.frame_rate_calc = 1/time1

            # Press 'q' to quit
            if cv2.waitKey(1) == ord('q'):
                break

        # Clean up
        cv2.destroyAllWindows()
        self.videostream.stop()

    def detect_from_frame(self, frame):
        # Acquire frame and resize to expected shape [1xHxWx3]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, (self.width, self.height))
        input_data = np.expand_dims(frame_resized, axis=0)

        # Normalize pixel values if using a floating model (i.e. if model is non-quantized)
        if self.floating_model:
            input_data = (np.float32(input_data) - INPUT_MEAN) / INPUT_STD

        # Perform the actual detection by running the model with the image as input
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()

        # Retrieve detection results
        boxes = self.interpreter.get_tensor(self.output_details[self.boxes_idx]['index'])[0] # Bounding box coordinates of detected objects
        classes = self.interpreter.get_tensor(self.output_details[self.classes_idx]['index'])[0] # Class index of detected objects
        scores = self.interpreter.get_tensor(self.output_details[self.scores_idx]['index'])[0] # Confidence of detected objects
        
        return boxes, classes, scores

    def calculate_ref_image_object_width(self, imagePath : str, wantedObjectName : str):
        image = cv2.imread(imagePath)
        boxes, classes, scores = self.detect_from_frame(image)
        imageWidth = -1

        for i in range(len(scores)):
            if ((scores[i] > self.min_threshold) and (scores[i] <= 1.0)):
                # Get bounding box coordinates and draw box
                # Interpreter can return coordinates that are outside of image dimensions, need to force them to be within image using max() and min()
                ymin = int(max(1,(boxes[i][0] * self.imH)))
                xmin = int(max(1,(boxes[i][1] * self.imW)))
                ymax = int(min(self.imH,(boxes[i][2] * self.imH)))
                xmax = int(min(self.imW,(boxes[i][3] * self.imW)))
                                    
                object_name = self.labels[int(classes[i])] # Look up object name from "labels" array using class index

                # TODO: remove this
                #testing distance
                print("detected object name: ", object_name)
                print("wanted object name: ", wantedObjectName)

                if (object_name == wantedObjectName):
                    imageWidth = (xmax-xmin)
                    break
        
        return imageWidth

    def focal_length_finder (self, real_measured_distance, real_object_width, width_in_pixels):
        focal_length = (width_in_pixels * real_measured_distance) / real_object_width

        return focal_length

    def distance_finder(self, focal_length, real_object_width, object_current_width_in_frmae):
        distance = (real_object_width * focal_length) / object_current_width_in_frmae
        
        return distance