import subprocess
import platform
from os.path import join
from os import makedirs
import os
import sys
import regex as re
import json
from subprocess import check_call, STDOUT, CalledProcessError
from tools import write_file
import logging
from process_site_dumps import process_site_dumps, BASE_DUMP_PATH

"""
Script to download the data sources using wget, and then split all pages into document extracts for 
downstream tasks.
"""

redirect_log_re = re.compile('http[^\n]*(\n[^\n]*){2}301 Moved Permanently\nLocation:\s[^\n\s]*')

def pull_sites(base_urls, names, system_os, regex_rules = {}, output_folder = './', additional_urls_file = None, wget_exe_path = './wget.exe', wget_config_path = './wget_config.txt'):
    """
    Uses wget to pull the indicated websites, and processes
    the files into one combined csv of documents for use in the UBC Science 
    Advising question answering system.
    - base_urls: base urls to begin recursively searching from. Will grab all child pages.
    - names: list of names for each base url, used as a short form in logs
    - regex_rules: dict of names to regex rules to use to identify pages to include
                   if no entry specified for a name, pulls all child pages
    - output_folder: folder for output site dumps
    - additional_urls_file: .txt list of additional urls to pull (non recursively)
    - wget_exe_path: path to the wget.exe file
    - wget_config_path: path to the wget config file (aka .wgetrc)
    """
    # create the output dir if not exists, otherwise do nothing
    makedirs(output_folder, exist_ok=True)
    redirects = {}
    total_num = 0
    for base_url, name in zip(base_urls,names):
        logging.info(name)
        log_file = join(output_folder,f'wget_log_{name}.txt')
        rule_arg = None
        if name in regex_rules:
            rule_arg = f'--accept-regex=({regex_rules[name]})'
        else:
            rule_arg = '--no-parent'
            
        try:
            logging.info(f'- Beginning pull from {base_url}, making call to wget')
            logging.info(f'    - ** This may take a long time')
            logging.info(f'    - Check the log file {log_file} for updates')
            if system_os == "Windows":
                check_call([wget_exe_path, f'--config={wget_config_path}', f'--output-file={log_file}', '--recursive', 
                            f'--directory-prefix={output_folder}', rule_arg, base_url], stderr=STDOUT)
            elif system_os in ["Darwin", "Linux"]:
                check_call(["wget", f'--config={wget_config_path}', f'--output-file={log_file}', '--recursive', 
                            f'--directory-prefix={output_folder}', rule_arg, base_url], stderr=STDOUT)
            else:
                logging.error(f"OS {system_os} is not currently supported. Currently supported OS are Windows, Darwin and Linux")
                raise OSError(f"OS {system_os} is not currently supported")
            logging.info(f'- Successfully pulled from {base_url}')
        except CalledProcessError as exc:
            if exc.returncode == 8:
                # Server error return code
                logging.warning('- wget returned code 8, indicating server error:' 
                                + 'this will occur if it comes across any 404 error, so it is expected for the Academic Calendar.' 
                                + 'Please check that files were downloaded correctly.')
            else: 
                logging.error('- Call to wget failed')
                logging.error(f'- Error message: {exc.output}' if exc.output else 'No error message given')
                logging.error(f'- Skipping pull for {base_url}')
                continue
        
        total_num += get_redirects_from_log(log_file, redirects)

    if additional_urls_file:
        logging.info('Additional urls')
        log_file = f'wget_log_additional.txt'
        logging.info(f'- Beginning pull for additional urls listed in {additional_urls_file}, making call to wget')
        if system_os == "Windows":
            subprocess.check_call([wget_exe_path, f'--config={wget_config_path}', f'--output-file={log_file}', 
                                f'--input-file={additional_urls_file}', f'--directory-prefix={output_folder}'])
        elif system_os in ["Darwin", "Linux"]:
            subprocess.check_call(["wget", f'--config={wget_config_path}', f'--output-file={log_file}', 
                                f'--input-file={additional_urls_file}', f'--directory-prefix={output_folder}'])
        else:
            logging.error(f"OS {system_os} is not currently supported. Currently supported OS are Windows, Darwin and Linux")
            raise OSError(f"OS {system_os} is not currently supported")
        logging.info(f'- Completed pull for additional urls')
        get_redirects_from_log(log_file, redirects)
    
    # Cleanup copied files
    logging.info("Cleanup any duplicated files from wget")
    cleanup_copy_files(output_folder)
    
    redirects_path = join(output_folder,'redirects.txt')
    def writer(): 
        makedirs(output_folder, exist_ok=True)
        with open(redirects_path,'w') as f: json.dump(redirects,f)
    
    write_file(writer)
    print(f'Completed pulling sites, downloaded {total_num} pages')

def cleanup_copy_files(filepath):
    """
    wget will sometimes name the new version of a file as <name>.1.html,
    we want to rename it to <name>.html and delete the previous version
    """
    for root, _, files in os.walk(filepath):
        for name in files:
            splitname = name.split('.')
            if len(splitname) == 3 and splitname[1] == '1':
                # this is a new version of a file
                orig_name = f'{splitname[0]}.{splitname[2]}'
                copy_filepath = os.path.join(root, name)
                orig_filepath = os.path.join(root, orig_name)
                try: os.remove(orig_filepath) # remove the old version of the file
                except OSError: pass
                os.rename(copy_filepath,orig_filepath) # rename copy file to original file

def get_redirects_from_log(log_file, redirects):
    """
    Given a wget log file (on verbose mode), adds any redirected urls to the redirects dict
    Also returns the total number of URLs processed from the log
    """
    logging.info('- Getting redirects from the log file')
    total_num = 0
    with open(log_file,'r') as f: 
        initial_url = None
        redirected = False
        for line in f: # read line by line since the log file could be large
            if re.match(r'Saving to: \'[^\n\s]*\'',line):
                total_num += 1
            elif match := re.search('(?<=--\s\s)[^\n\s]*',line):
                initial_url = match.captures()[0]
                redirected = False
            elif '301 Moved Permanently' in line:
                redirected = True
            elif redirected and (match := re.search('(?<=Location: )[^\n\s]*',line)):
                final_url = match.captures()[0]
                redirects[initial_url] = final_url
    logging.info('- Completed processing redirects')
    return total_num

### Main

def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # check the system OS since Windows Machine requires a wget.exe
    # darwin (OS X) and Linux probably not
    system_os = platform.system()
    logging.info(f"System OS: {system_os}")
    wget_exe_path = "wget.exe"
    wget_config_path = 'wget_config.txt'

    urls = [
        'https://vancouver.calendar.ubc.ca/',
        'https://science.ubc.ca/students/'
    ]
    names = [
        'academic_calendar',
        'science_students'
    ]
    regex_rules = {
        'science_students': '.*science.ubc.ca/students.*'
    }

    pull_sites(urls,names,system_os,regex_rules,output_folder = BASE_DUMP_PATH, wget_exe_path=wget_exe_path, wget_config_path=wget_config_path)
    process_site_dumps()

if __name__ == '__main__':
    main()
