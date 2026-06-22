# AI Module

# Fish Stress Detection - AI Module

## Objective

Detect fish in underwater videos and analyze fish behavior using computer vision techniques for aquaculture monitoring.

## Features

* Fish Detection using YOLOv8
* Fish Counting
* Fish Tracking using ByteTrack
* Fish Movement Analysis
* Fish Density Analysis
* Individual Fish Behavior Analysis
* Speed Calculation
* Speed Variability Analysis
* Inactivity Detection
* Surface Visit Monitoring
* Bottom Dwelling Analysis

## Results

| Metric                        | Value      |
| ----------------------------- | ---------- |
| Average Fish Count            | 6.97       |
| Maximum Fish Count            | 18         |
| Minimum Fish Count            | 1          |
| Coefficient of Variation      | 43.99%     |
| Average Fish Distance         | 784 pixels |
| Average Speed                 | 15.97      |
| Unique Fish IDs Detected      | 1004       |
| Reliable Fish Tracks Analyzed | 52         |

## Behavioral Metrics Computed

For each reliably tracked fish:

* Average Speed
* Speed Variability
* Inactivity Percentage
* Surface Visits
* Bottom Dwelling Percentage

These behavioral metrics are exported for further stress assessment and integration with environmental sensor data.

## Outputs

* fish_stress_best.pt
* fish_stress_project_best.pt
* fish_tracking.csv
* individual_fish_stress.csv

## Workflow

Dataset Preparation

↓

Annotation

↓

YOLOv8 Training

↓

Fish Detection

↓

Fish Tracking

↓

Coordinate Extraction

↓

Behavioral Feature Extraction

↓

Individual Fish Behavior Analysis

↓

CSV Output Generation

## Status

✅ Dataset Preparation

✅ Annotation

✅ YOLO Training

✅ Fish Detection

✅ Fish Counting

✅ Fish Tracking

✅ Fish Density Analysis

✅ Fish Movement Analysis

✅ Behavioral Feature Extraction

✅ Individual Fish Behavior Analysis

✅ CSV Output Generation

## Future Integration

The AI module generates behavioral metrics for individual fish. These metrics will be integrated with:

* Water Temperature Sensor
* pH Sensor
* Dissolved Oxygen Sensor
* Turbidity Sensor
* TDS Sensor

through the backend module to compute the final Fish Stress Index (FSI).

## Team Member

Likhita Reddy
