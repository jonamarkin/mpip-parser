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
import uuid # Import uuid for generating unique document IDs
from pathlib import Path

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    print("Firebase Admin SDK not found. Please install it using: pip install firebase-admin")
    # Exit gracefully if Firebase Admin SDK is not installed
    import sys
    sys.exit(1)

class MPIPParser:
    def __init__(self):
        self.data = {}
        
    def parse_file(self, filepath: str, provided_interface_type: Optional[str] = None) -> Dict:
        """
        Parse a single mpiP profiling file.
        Args:
            filepath (str): The path to the mpiP log file.
            provided_interface_type (Optional[str]): The interface type (e.g., 'tcp', 'opx')
                                                     provided by the user. Defaults to None.
        Returns:
            Dict: A dictionary containing the parsed data.
        """
        # FIX: Changed encoding to 'latin-1' to handle potential UnicodeDecodeError
        with open(filepath, 'r', encoding='latin-1') as f: 
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
        
        # Determine interface type: prioritize provided_interface_type, then try to infer from env var in log
        interface_type = provided_interface_type if provided_interface_type else self._infer_interface_from_log(content)
        
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
            command_str = command_match.group(1).strip()
            info['command'] = command_str
            
            # NEW: Extract batch size from the command string
            batch_size_match = re.search(r'--batch-size\s+(\d+)', command_str)
            if batch_size_match:
                info['batch_size'] = int(batch_size_match.group(1))
            else:
                info['batch_size'] = 'N/A' # Default if not found
        
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

        # MPIP env var (for interface inference if not provided by user)
        env_var_match = re.search(r'@ MPIP env var\s*:\s*(.+)', content)
        if env_var_match:
            info['mpip_env_var'] = env_var_match.group(1).strip()
        
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
                            # Handle multi-word call_type like 'Allreduce' or 'MPI_Comm_rank'
                            call_type_parts = []
                            idx = 0
                            while idx < len(parts) and not parts[idx].isdigit():
                                call_type_parts.append(parts[idx])
                                idx += 1
                            call_type = ' '.join(call_type_parts)

                            remaining_parts = parts[idx:]
                            if len(remaining_parts) >= 6:
                                stats['operations'].append({
                                    'call_type': call_type,
                                    'site': int(remaining_parts[0]),
                                    'time_ms': float(remaining_parts[1]),
                                    'app_percentage': float(remaining_parts[2]),
                                    'mpi_percentage': float(remaining_parts[3]),
                                    'count': int(remaining_parts[4]),
                                    'cov': float(remaining_parts[5])
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
                            # Handle multi-word call_type
                            call_type_parts = []
                            idx = 0
                            while idx < len(parts) and not parts[idx].isdigit():
                                call_type_parts.append(parts[idx])
                                idx += 1
                            call_type = ' '.join(call_type_parts)

                            remaining_parts = parts[idx:]
                            if len(remaining_parts) >= 5:
                                stats['operations'].append({
                                    'call_type': call_type,
                                    'site': int(remaining_parts[0]),
                                    'count': int(remaining_parts[1]),
                                    'total_bytes': float(remaining_parts[2]),
                                    'avg_bytes': float(remaining_parts[3]),
                                    'sent_percentage': float(remaining_parts[4])
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
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        # Handle multi-word name
                        name_parts = []
                        idx = 0
                        while idx < len(parts) and not parts[idx].isdigit():
                            name_parts.append(parts[idx])
                            idx += 1
                        name = ' '.join(name_parts)

                        remaining_parts = parts[idx:]
                        if len(remaining_parts) >= 8:
                            stats['callsites'].append({
                                'name': name,
                                'site': int(remaining_parts[0]),
                                'rank': int(remaining_parts[1]) if remaining_parts[1] != '*' else 'aggregate',
                                'count': int(remaining_parts[2]),
                                'max_time': float(remaining_parts[3]),
                                'mean_time': float(remaining_parts[4]),
                                'min_time': float(remaining_parts[5]),
                                'app_percentage': float(remaining_parts[6]),
                                'mpi_percentage': float(remaining_parts[7])
                            })
                    except ValueError:
                        continue
        
        return stats
    
    def _infer_interface_from_log(self, content: str) -> str:
        """
        Infers interface type from the 'MPIP env var' in the log content.
        Defaults to 'unknown' if not found or recognized.
        """
        env_var_match = re.search(r'@ MPIP env var\s*:\s*(.+)', content)
        if env_var_match:
            env_var_value = env_var_match.group(1).lower()
            if 'mpip_tcp' in env_var_value:
                return 'tcp'
            elif 'mpip_opx' in env_var_value or 'omni' in env_var_value:
                return 'opx'
        return 'unknown'
    
    def _generate_summary(self, run_info: Dict, mpi_time_stats: Dict, aggregate_time_stats: Dict) -> Dict:
        """Generate summary statistics"""
        summary = {}
        
        # Basic info
        summary['num_processes'] = run_info.get('num_processes', 0)
        summary['num_nodes'] = run_info.get('num_nodes', 0)
        summary['batch_size'] = run_info.get('batch_size', 'N/A') # NEW: Add batch_size to summary
        
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
        # num_nodes = data['run_info']['num_nodes'] # No longer directly in path
        batch_size = data['run_info'].get('batch_size', 'N/A') 

        # Use a more robust collection path structure for user-specific data
        # artifacts/{appId}/users/{userId}/mpiP_experiments/{interface_type}/{batch_size}_batchsize/{documentId}
        app_id = "thesis" # Can be customized
        user_id = "jonamarkin" # Can be customized or passed as arg

        # UPDATED: Collection path now only includes interface_type and batch_size
        collection_path = f"artifacts/{app_id}/users/{user_id}/mpiP_experiments/{interface_type}/{batch_size}_batchsize"
        
        # Generate a unique document ID using UUID
        doc_id = f"{uuid.uuid4().hex}" 
        
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
    parser.add_argument('--interface-type', type=str, default='unknown',
                        help='Specify the interface type (e.g., "tcp", "opx"). Defaults to "unknown" or inferred from log.')
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
            # FIX: Added '.mpiP' to the list of recognized suffixes
            if file_path.is_file() and file_path.suffix in ['.txt', '.out', '.log', '', '.mpiP'] and file_path.stat().st_size > 0:
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
            # Pass the provided interface type to the parser
            data = mpip_parser.parse_file(file_path, provided_interface_type=args.interface_type)
            parsed_experiments.append(data)
            print(f"  - Interface: {data['interface_type']}, Nodes: {data['run_info']['num_nodes']}, Batch Size: {data['run_info'].get('batch_size', 'N/A')}, MPI%: {data['summary'].get('total_mpi_percentage', 'N/A')}")
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
    batch_size_counts = {} # NEW: Track batch size counts
    
    for exp in parsed_experiments:
        interface = exp['interface_type']
        nodes = exp['run_info']['num_nodes']
        batch_size = exp['run_info'].get('batch_size', 'N/A') # NEW: Get batch size

        interface_counts[interface] = interface_counts.get(interface, 0) + 1
        node_counts[nodes] = node_counts.get(nodes, 0) + 1
        batch_size_counts[batch_size] = batch_size_counts.get(batch_size, 0) + 1 # NEW: Increment batch size count
    
    print(f"Total experiments: {len(parsed_experiments)}")
    print(f"By interface: {interface_counts}")
    print(f"By node count: {node_counts}")
    print(f"By batch size: {batch_size_counts}") # NEW: Print batch size summary

if __name__ == "__main__":
    main()
