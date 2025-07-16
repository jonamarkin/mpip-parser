# mpiP Profiling Data Management

This project provides tools to parse, organize, and store mpiP profiling results in a Firebase Firestore database. It includes a Python script for batch processing log files and a React web application for interactive parsing and management of individual logs. The goal is to facilitate easier analysis, visualization, and comparison of MPI application performance across different configurations (e.g., communication interfaces, number of nodes).

## Features

* **Automated Log Parsing**: Extracts detailed performance metrics from mpiP profiling output.

* **Structured Data Storage**: Stores parsed data in a well-organized JSON format within Firebase Firestore.

* **Categorization**: Automatically categorizes experiments by communication interface (TCP, OPX) and the number of MPI nodes used.

* **Batch Processing (Python Script)**: Process multiple mpiP log files from a specified directory.

* **Interactive Web UI (React App)**: A user-friendly interface to paste individual mpiP logs, parse them, and save them to Firestore, with immediate feedback and a list of stored experiments.

* **Scalable Storage**: Leverages Firebase Firestore for reliable and scalable data persistence.

* **Analysis Ready**: The structured data is ideal for further analysis, plotting graphs, and averaging results using tools like Python (Pandas, Matplotlib), R, or dedicated visualization dashboards.

## Technologies Used

* **Python**: For the backend parsing script.

  * `firebase-admin`: To interact with Firebase Firestore.

  * `os`, `re`, `json`, `datetime`, `uuid`, `sys`: Standard Python libraries for file operations, regex, data handling, and unique ID generation.

* **React**: For the frontend web application.

  * `Firebase SDK (JavaScript)`: For client-side interaction with Firestore and Authentication.

  * `Tailwind CSS`: For responsive and modern UI styling.

* **Firebase Firestore**: NoSQL cloud database for storing the structured mpiP data.

* **mpiP**: The MPI profiling tool whose output this project processes.

## Setup and Installation

### 1. Firebase Project Setup

Before using either the Python script or the React app, you need to set up a Firebase project:

1. **Create a Firebase Project**: Go to the [Firebase Console](https://console.firebase.google.com/) and create a new project.

2. **Enable Firestore**: In your Firebase project, navigate to "Build" > "Firestore Database" and create a new database (choose "Start in production mode" for security, but remember to set up proper security rules later).

3. **Security Rules**: For this project, we assume the following basic Firestore security rules, which allow authenticated users to read and write to their own data:

   ```firestore
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       // Public data (if you want to share data between users, e.g., for collaborative apps)
       match /artifacts/{appId}/public/data/{collection}/{document} {
         allow read, write: if request.auth != null;
       }
   
       // Private data (default for this project)
       match /artifacts/{appId}/users/{userId}/{collection}/{document} {
         allow read, write: if request.auth != null && request.auth.uid == userId;
       }
     }
   }
   ```

### 2. Python Script Setup

1. **Clone the Repository**:

   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

2. **Install Dependencies**:

   ```bash
   pip install firebase-admin
   ```

3. **Get Firebase Service Account Key**:

   * In your Firebase Console, go to **Project settings** (gear icon) > **Service accounts**.

   * Click **Generate new private key**. A JSON file will be downloaded. **Keep this file secure!**

   * Place this JSON file in a secure location on your machine (e.g., `~/.firebase/serviceAccountKey.json`).

4. **Configure Script (Optional)**:
   You can modify `APP_ID` and `USER_ID` variables at the top of the `mpiP_parser.py` script if you want to use specific identifiers other than the defaults (`default-mpiP-app` and `default-user`).

### 3. React Application Setup (for Canvas Environment)

The React application is designed to run within a Google Gemini Canvas environment.

1. **Firebase Configuration**: The React app expects Firebase configuration and authentication tokens to be provided via global variables (`__app_id`, `__firebase_config`, `__initial_auth_token`). These are automatically injected by the Canvas environment.

2. **No Local Setup Needed**: If you are running this within the Canvas environment, you do not need to manually set up `npm install` or `npm start`. The environment handles the dependencies and rendering.

## Usage

### Using the Python Script

The Python script allows you to process mpiP log files in a batch.

```bash
python mpiP_parser.py <path_to_log_file_or_folder> <path_to_firebase_service_account_key.json>
```

* `<path_to_log_file_or_folder>`:

  * If it's a **single file**, the script will process that file.

  * If it's a **folder**, the script will recursively search for `.txt`, `.log`, or files containing `mpip` in their name within that folder and process them.

* `<path_to_firebase_service_account_key.json>`: The absolute path to your Firebase service account key JSON file.

**Examples:**

```bash
# Process a single mpiP log file
python mpiP_parser.py /home/user/mpi_experiments/log_run_1.txt /path/to/your/serviceAccountKey.json

# Process all mpiP logs in a directory
python mpiP_parser.py /home/user/mpi_experiments /path/to/your/serviceAccountKey.json
```

### Using the React Application

The React application provides an interactive web interface.

1. **Access the Application**: Deploy or open the React application in your Google Gemini Canvas environment.

2. **Paste Log**: Copy the content of an mpiP profiling log file.

3. **Select Interface Type**: Choose the appropriate communication interface (TCP, OPX, or Unknown) from the dropdown. This helps categorize your data.

4. **Parse and Save**: Click the "Parse and Save to Firestore" button. The application will:

   * Parse the log content.

   * Extract structured data.

   * Infer the number of nodes.

   * Store the data as a new document in your Firebase Firestore database.

   * Display the parsed JSON data for immediate review.

   * Update the list of "Your Stored Experiments".

5. **Manage Experiments**: You can view a list of all experiments stored by your user ID and delete them as needed.

## Data Structure in Firebase Firestore

All parsed mpiP experiment data will be stored in a collection named `mpiP_experiments` under the path:
`artifacts/{appId}/users/{userId}/mpiP_experiments/{documentId}`

Each document (representing one experiment run) will have a structure similar to this:

```json
{
  "appId": "default-mpiP-app",
  "userId": "default-user",
  "fileName": "your_log_file_name.txt",
  "filePath": "/path/to/your/log/file/your_log_file_name.txt",
  "timestamp": "2025-07-16T13:18:00.123456",
  "Command": "python /home/j.markin/torch_projects/resnet50_cifar100_updatefreq.py --epochs 10 --batch-size 8 --log-interval 1",
  "Version": "3.5.0",
  "MPIPBuilddate": "Dec 14 2023, 13:17:54",
  "Starttime": "2025 07 14 07:13:08",
  "Stoptime": "2025 07 14 07:42:52",
  "TimerUsed": "PMPI_Wtime",
  "MPIPenvvar": "-f /home/j.markin/torch_projects/mpip_tcp_new_results_8",
  "CollectorRank": "0",
  "CollectorPID": "3840025",
  "FinalOutputDir": "/home/j.markin/torch_projects/mpip_tcp_new_results_8",
  "Reportgeneration": "Single collector task",
  "interfaceType": "tcp",
  "mpiTaskAssignments": [
    { "task": 0, "node": "node01" },
    { "task": 1, "node": "node02" }
  ],
  "numNodes": 16,
  "durationSeconds": 1784.0,
  "mpiTimeSummary": {
    "tasks": [
      { "task": 0, "appTime": 1780.0, "mpiTime": 1320.0, "mpiPercent": 73.76 }
    ],
    "aggregate": { "task": "*", "appTime": 28600.0, "mpiTime": 20800.0, "mpiPercent": 72.92 }
  },
  "callsites": [
    {
      "id": 1,
      "level": 0,
      "fileAddress": "0x7f99c641da6c",
      "line": null,
      "parentFunction": "aoti_torch_cpu__foreach_reciprocal_",
      "mpiCall": "Allreduce"
    }
  ],
  "aggregateTime": [
    {
      "call": "Allreduce",
      "site": 22,
      "time": 1310000.0,
      "appPercent": 4.59,
      "mpiPercent": 6.29,
      "count": 19546,
      "cov": 0.0
    }
  ],
  "aggregateSentMessageSize": [
    {
      "call": "Allreduce",
      "site": 1,
      "count": 19546,
      "total": 400000000000.0,
      "average": 20400000.0,
      "sentPercent": 6.24
    }
  ],
  "callsiteTimeStatistics": [
    {
      "name": "Allgather",
      "site": 3,
      "rank": 0,
      "count": 1,
      "max": 113.0,
      "mean": 113.0,
      "min": 113.0,
      "appPercent": 0.01,
      "mpiPercent": 0.01
    }
  ],
  "callsiteMessageSentStatistics": [
    {
      "name": "Allgather",
      "site": 3,
      "rank": 0,
      "count": 1,
      "max": 8.0,
      "mean": 8.0,
      "min": 8.0,
      "sum": 8.0
    }
  ]
}
```

## Future Enhancements

* **Advanced Parsing**: Improve parsing robustness for more varied mpiP output formats or corrupted logs.

* **Data Visualization**: Integrate plotting libraries (e.g., Matplotlib/Seaborn in Python, D3.js/Recharts in React) directly into the web application for on-the-fly visualization of stored data.

* **Comparison Tools**: Add features to compare multiple experiment runs side-by-side.

* **Filtering and Search**: Implement more advanced filtering and search capabilities within the React app.

* **Export Options**: Allow users to export stored data to CSV, JSON, or other formats for external analysis.

* **User Management**: Implement more sophisticated user authentication and data sharing features if needed for collaborative environments.

## License

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).
