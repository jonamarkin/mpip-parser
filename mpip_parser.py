"""
MPI Profiling Results Parser and Firebase Uploader
Parses mpiP profiling output files and stores structured data in Firebase
"""

import os
import re
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Union
import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path

class MPIPParser:
    def __init__(self):
        self.data = {}
        
    def parse_file(self, filepath: str) -> Dict:
        """Parse a single mpiP profiling file"""
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Extract basic run information
        run_info = self._extract_run_info(content)
        
        # Extract MPI time statistics
        mpi_time_stats = self._extract_mpi_time_stats(content)
        
        # Extract aggregate time statistics
        aggregate_time_stats = self._extract_aggregate_time_stats(content)
        
        # Extract message size statistics
        message_size_stats = self._extract_message_size_stats(content)
        
        # Extract callsite statistics
        callsite_stats = self._extract_callsite_stats(content)
        
        # Determine interface type from filename or path
        interface_type = self._determine_interface_type(filepath)
        
        # Compile all data
        parsed_data = {
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'interface_type': interface_type,
            'run_info': run_info,
            'mpi_time_stats': mpi_time_stats,
            'aggregate_time_stats': aggregate_time_stats,
            'message_size_stats': message_size_stats,
            'callsite_stats': callsite_stats,
            'parsing_timestamp': datetime.now().isoformat(),
            'summary': self._generate_summary(run_info, mpi_time_stats, aggregate_time_stats)
        }
        
        return parsed_data
    
    def _extract_run_info(self, content: str) -> Dict:
        """Extract basic run information"""
        info = {}
        
        # Command
        command_match = re.search(r'@ Command\s*:\s*(.+)', content)
        if command_match:
            info['command'] = command_match.group(1).strip()
        
        # Version
        version_match = re.search(r'@ Version\s*:\s*(.+)', content)
        if version_match:
            info['version'] = version_match.group(1).strip()
        
        # Start and stop times
        start_match = re.search(r'@ Start time\s*:\s*(.+)', content)
        if start_match:
            info['start_time'] = start_match.group(1).strip()
            
        stop_match = re.search(r'@ Stop time\s*:\s*(.+)', content)
        if stop_match:
            info['stop_time'] = stop_match.group(1).strip()
        
        # Extract task assignments (nodes)
        task_assignments = []
        task_pattern = r'@ MPI Task Assignment\s*:\s*(\d+)\s+(\S+)'
        for match in re.finditer(task_pattern, content):
            task_assignments.append({
                'rank': int(match.group(1)),
                'node': match.group(2)
            })
        
        info['task_assignments'] = task_assignments
        info['num_processes'] = len(task_assignments)
        
        # Extract unique nodes
        unique_nodes = list(set(task['node'] for task in task_assignments))
        info['nodes'] = unique_nodes
        info['num_nodes'] = len(unique_nodes)
        
        return info
    
    def _extract_mpi_time_stats(self, content: str) -> Dict:
        """Extract MPI time statistics table"""
        stats = {}
        
        # Find the MPI Time section
        time_section = re.search(r'@--- MPI Time \(seconds\) ---.*?\n(.*?)\n-----------', content, re.DOTALL)
        if time_section:
            lines = time_section.group(1).strip().split('\n')
            task_stats = []
            
            for line in lines:
                if line.strip() and not line.startswith('Task'):
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            task_stats.append({
                                'task': int(parts[0]) if parts[0] != '*' else 'aggregate',
                                'app_time': float(parts[1]),
                                'mpi_time': float(parts[2]),
                                'mpi_percentage': float(parts[3])
                            })
                        except ValueError:
                            continue
            
            stats['task_stats'] = task_stats
            
            # Extract aggregate stats (marked with *)
            aggregate_stats = [s for s in task_stats if s['task'] == 'aggregate']
            if aggregate_stats:
                stats['aggregate'] = aggregate_stats[0]
        
        return stats
    
    def _extract_aggregate_time_stats(self, content: str) -> Dict:
        """Extract aggregate time statistics"""
        stats = {'operations': []}
        
        # Find the Aggregate Time section
        agg_section = re.search(r'@--- Aggregate Time \(top twenty.*?\n(.*?)\n-----------', content, re.DOTALL)
        if agg_section:
            lines = agg_section.group(1).strip().split('\n')
            
            for line in lines:
                if line.strip() and not line.startswith('Call'):
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            stats['operations'].append({
                                'call_type': parts[0],
                                'site': int(parts[1]),
                                'time_ms': float(parts[2]),
                                'app_percentage': float(parts[3]),
                                'mpi_percentage': float(parts[4]),
                                'count': int(parts[5]),
                                'cov': float(parts[6]) if len(parts) > 6 else 0.0
                            })
                        except ValueError:
                            continue
        
        return stats
    
    def _extract_message_size_stats(self, content: str) -> Dict:
        """Extract message size statistics"""
        stats = {'operations': []}
        
        # Find the Message Size section
        msg_section = re.search(r'@--- Aggregate Sent Message Size.*?\n(.*?)\n-----------', content, re.DOTALL)
        if msg_section:
            lines = msg_section.group(1).strip().split('\n')
            
            for line in lines:
                if line.strip() and not line.startswith('Call'):
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            stats['operations'].append({
                                'call_type': parts[0],
                                'site': int(parts[1]),
                                'count': int(parts[2]),
                                'total_bytes': float(parts[3]),
                                'avg_bytes': float(parts[4]),
                                'sent_percentage': float(parts[5]) if len(parts) > 5 else 0.0
                            })
                        except ValueError:
                            continue
        
        return stats
    
    def _extract_callsite_stats(self, content: str) -> Dict:
        """Extract detailed callsite statistics"""
        stats = {'callsites': []}
        
        # Find the Callsite Time statistics section
        callsite_section = re.search(r'@--- Callsite Time statistics.*?\n(.*?)\n-----------', content, re.DOTALL)
        if callsite_section:
            lines = callsite_section.group(1).strip().split('\n')
            
            current_operation = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        stats['callsites'].append({
                            'name': parts[0],
                            'site': int(parts[1]),
                            'rank': int(parts[2]) if parts[2] != '*' else 'aggregate',
                            'count': int(parts[3]),
                            'max_time': float(parts[4]),
                            'mean_time': float(parts[5]),
                            'min_time': float(parts[6]),
                            'app_percentage': float(parts[7]),
                            'mpi_percentage': float(parts[8]) if len(parts) > 8 else 0.0
                        })
                    except ValueError:
                        continue
        
        return stats
    
    def _determine_interface_type(self, filepath: str) -> str:
        """Determine interface type from filename or path"""
        filepath_lower = filepath.lower()
        if 'tcp' in filepath_lower:
            return 'tcp'
        elif 'opx' in filepath_lower or 'omni' in filepath_lower:
            return 'opx'
        else:
            return 'unknown'
    
    def _generate_summary(self, run_info: Dict, mpi_time_stats: Dict, aggregate_time_stats: Dict) -> Dict:
        """Generate summary statistics"""
        summary = {}
        
        # Basic info
        summary['num_processes'] = run_info.get('num_processes', 0)
        summary['num_nodes'] = run_info.get('num_nodes', 0)
        
        # MPI overhead
        if 'aggregate' in mpi_time_stats:
            summary['total_mpi_percentage'] = mpi_time_stats['aggregate']['mpi_percentage']
            summary['total_app_time'] = mpi_time_stats['aggregate']['app_time']
            summary['total_mpi_time'] = mpi_time_stats['aggregate']['mpi_time']
        
        # Top operations
        if aggregate_time_stats['operations']:
            summary['top_operations'] = aggregate_time_stats['operations'][:5]
            
            # Count operations by type
            op_counts = {}
            op_times = {}
            for op in aggregate_time_stats['operations']:
                op_type = op['call_type']
                op_counts[op_type] = op_counts.get(op_type, 0) + 1
                op_times[op_type] = op_times.get(op_type, 0) + op['time_ms']
            
            summary['operation_counts'] = op_counts
            summary['operation_times'] = op_times
        
        return summary

class FirebaseUploader:
    def __init__(self, credentials_path: str):
        """Initialize Firebase connection"""
        if not firebase_admin._apps:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred)
        
        self.db = firestore.client()
    
    def upload_experiment(self, data: Dict) -> str:
        """Upload experiment data to Firebase"""
        interface_type = data['interface_type']
        num_nodes = data['run_info']['num_nodes']
        
        # Create collection path: experiments/{interface_type}/{num_nodes}_nodes
        collection_path = f"experiments/{interface_type}/{num_nodes}_nodes"
        
        # Generate document ID with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"experiment_{timestamp}_{data['filename']}"
        
        # Upload to Firebase
        doc_ref = self.db.collection(collection_path).document(doc_id)
        doc_ref.set(data)
        
        print(f"Uploaded to: {collection_path}/{doc_id}")
        return doc_id
    
    def batch_upload(self, experiments: List[Dict]) -> List[str]:
        """Upload multiple experiments in batch"""
        doc_ids = []
        
        for experiment in experiments:
            try:
                doc_id = self.upload_experiment(experiment)
                doc_ids.append(doc_id)
            except Exception as e:
                print(f"Failed to upload {experiment.get('filename', 'unknown')}: {e}")
        
        return doc_ids

def main():
    parser = argparse.ArgumentParser(description='Parse mpiP profiling results and upload to Firebase')
    parser.add_argument('input_path', help='Path to file or directory containing mpiP results')
    parser.add_argument('--credentials', required=True, help='Path to Firebase credentials JSON file')
    parser.add_argument('--output-json', help='Also save parsed data to JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Parse files but don\'t upload to Firebase')
    
    args = parser.parse_args()
    
    # Initialize parser
    mpip_parser = MPIPParser()
    
    # Find all files to process
    files_to_process = []
    input_path = Path(args.input_path)
    
    if input_path.is_file():
        files_to_process = [str(input_path)]
    elif input_path.is_dir():
        # Find all text files in directory
        for file_path in input_path.rglob('*'):
            if file_path.is_file() and file_path.suffix in ['.txt', '.out', '.log', ''] and file_path.stat().st_size > 0:
                files_to_process.append(str(file_path))
    else:
        print(f"Error: {input_path} is not a valid file or directory")
        return
    
    if not files_to_process:
        print("No files found to process")
        return
    
    print(f"Found {len(files_to_process)} files to process")
    
    # Parse all files
    parsed_experiments = []
    for file_path in files_to_process:
        try:
            print(f"Parsing: {file_path}")
            data = mpip_parser.parse_file(file_path)
            parsed_experiments.append(data)
            print(f"  - Interface: {data['interface_type']}, Nodes: {data['run_info']['num_nodes']}, MPI%: {data['summary'].get('total_mpi_percentage', 'N/A')}")
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
    
    # Save to JSON if requested
    if args.output_json:
        with open(args.output_json, 'w') as f:
            json.dump(parsed_experiments, f, indent=2)
        print(f"Saved parsed data to {args.output_json}")
    
    # Upload to Firebase unless dry run
    if not args.dry_run:
        try:
            uploader = FirebaseUploader(args.credentials)
            uploaded_ids = uploader.batch_upload(parsed_experiments)
            print(f"Successfully uploaded {len(uploaded_ids)} experiments to Firebase")
        except Exception as e:
            print(f"Error uploading to Firebase: {e}")
    else:
        print("Dry run mode - skipping Firebase upload")
    
    # Print summary
    print("\n=== SUMMARY ===")
    interface_counts = {}
    node_counts = {}
    
    for exp in parsed_experiments:
        interface = exp['interface_type']
        nodes = exp['run_info']['num_nodes']
        
        interface_counts[interface] = interface_counts.get(interface, 0) + 1
        node_counts[nodes] = node_counts.get(nodes, 0) + 1
    
    print(f"Total experiments: {len(parsed_experiments)}")
    print(f"By interface: {interface_counts}")
    print(f"By node count: {node_counts}")

if __name__ == "__main__":
    main()