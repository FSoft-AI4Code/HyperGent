import os.path as osp
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
import subprocess
from typing import List, Optional, Callable
from repopilot.llm_multilspy import add_num_line
from repopilot.agents.llms import LocalLLM, AzureLLM
import os
from repopilot.code_search import get_parser
from codetext.utils import parse_code
import re

summarizer = LocalLLM({"model": "google/gemma-2-27b-it", "system_prompt": "Describe this error message in plain text.", "max_tokens": 25000})
reviewer = AzureLLM({"model": "gpt-4-turbo", "system_prompt": "You're a software engineer working on a project, given a hint of code replacement of original file, you need to generate a block of code that can be replaced into the original. Do not generate additional line if it's unecessary to the hint. Pay attention to line number and indentation", "max_tokens": 10000})

class EditorArgs(BaseModel):
    relative_file_path: str = Field(..., description="The relative file path of the file that is need to be edited")
    start_line: int = Field(..., description="The line number to start the edit at")
    end_line: int = Field(..., description="The line number to end the edit at (inclusive)")
    patch: str = Field(..., description="""the code to replace the current selection with, make sure the code is syntactically correct, identation is correct, and the code resolved the request. Remember to add indentation to the block if the original code position is indented.
    Example: patch: "    def something(self, s):\n    # Check if something is something\n        return something" if the original code is indented with 4 spaces or "def something(self, s):\n    # Check if something is something\n        return something" if the original block is not indented. And "        def something(self, s):\n    # Check if something is something\n" if the block is idented with 8 spaces.
                       """)
    context: Optional[str] = Field(..., description="The context of why you are editing the file")

class EditorTool(BaseTool):
    name = "editor_file"
    description = """Useful when you want to edit a file inside a repo with alternative code."""
    args_schema = EditorArgs
    path = ""
    
    def __init__(self, path, language=None):
        super().__init__()
        self.path = path
    
    def _run(self, relative_file_path: str = None, start_line:int = None, end_line: int = None, patch: str = None, context: Optional[str] = None):
        """
        Opens the specified file and returns its content.

        Args:
            relative_file_path (str): The relative path to the file.
            max_new_line (int, optional): The maximum number of lines to include in the returned content. Defaults to 500.

        Returns:
            str: The content of the file.

        """        
        if relative_file_path is None:
            return "Please specify the relative file path that you want to edit."
        
        if not os.path.exists(osp.join(self.path, relative_file_path)):
            return "File not found, please check the path again"
        
        with open(osp.join(self.path, relative_file_path), 'r') as file:
            lines = file.readlines()
            
        if end_line is  None or end_line is None:
            return "Please specify either start and end line"
        
        if start_line < 1 or start_line > end_line:
            return f"Invalid start and end line (start line must be >0 and end line  < {len(lines)}), please check the line number again"
        
        if patch is None:
            return "Please specify the alterative code to replace the original code"
        
    
        # extracted_element = code_extract(lines, start_line, end_line)
        
        
        start_index = start_line - 1
        end_index = end_line
        updated_lines = lines[:start_index] + [patch+ "\n"] + lines[end_index:]
        
        
        initial_patch_lines_region = lines[max(0, start_index-10):start_index] + [patch + "\n"] + lines[end_index: min((end_index+10), len(lines))]
        initial_patch_block = "\n".join(initial_patch_lines_region)
        initial_patch_block = add_num_line(initial_patch_block, max(1, start_index-10)+1)
        
        original_lines_region = lines[max(0,start_index-10):min(end_index + 10, len(lines))]
        original_block = "\n".join(original_lines_region)
        original_block = add_num_line(original_block, max(0, start_index-10)+1)
        
        patch_file_path = osp.join(self.path, relative_file_path.split('.')[0] + '_patched.' + relative_file_path.split('.')[1])
        
        # review_command = f"Context of Editing: {context}\nStart and End line of Original Target Block: {start_line}:{end_line}. Your should only edit inside this range of lines.\nFile Name: {patch_file_path}\nOriginal Target Block with Surrounding Lines:\n```python\n{original_block}\n```\n\nProposed Block:\n```python\n{initial_patch_block}\n```\n\nThink step by step, understanding the original block of code and intention of Proposed Hint Patch generate a python block that is syntactically correct, identation is correct to both harmonize the original code and satisfy the intention of the proposed hint patch. Think about indetation, intent then generate a block in ```python ``` format without line numbers inside block but with identation. Your Thought:"
        # reviewer_output = reviewer(review_command)
        # pattern = re.compile(r'```python(.*?)```', re.DOTALL)
        # reviewed_patch = pattern.search(reviewer_output)
        
        os.chdir(self.path)
        
        review_success = False
        
        # if reviewed_patch:
        #     #apply the github diff patch
        #     updated_reviewed_lines = lines[:start_index] + [reviewed_patch.group(1)] + lines[end_index:]
        #     with open(patch_file_path, "w") as file:
        #         file.writelines(updated_reviewed_lines)
        #     command_fix = f"autopep8 --in-place --aggressive {patch_file_path}"
        #     result = subprocess.run(command_fix, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
        #     command = f"flake8 --isolated --select=F821,F822,F831,E111,E112,E113,E999,E902 {patch_file_path}"
        #     result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
        #     stderr_output = result.stderr
        #     stdout_output = result.stdout
        #     exit_code = result.returncode
        #     if exit_code == 0:
        #         with open(osp.join(self.path, relative_file_path), 'w') as file:
        #             file.writelines(updated_reviewed_lines)
        #         os.remove(patch_file_path)
        #         return f"Successfully edited the file {relative_file_path} from line {start_line} to {end_line}"
            
        # if not review_success:
        with open(patch_file_path, "w") as file:
            file.writelines(updated_lines)
        
        command_fix = f"autopep8 --in-place --aggressive {patch_file_path}"
        result = subprocess.run(command_fix, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        command = f"flake8 --isolated --select=F821,F822,F831,E111,E112,E113,E999,E902 {patch_file_path}"
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
        stderr_output = result.stderr
        stdout_output = result.stdout
        exit_code = result.returncode
        if exit_code == 0:
            with open(osp.join(self.path, relative_file_path), 'w') as file:
                file.writelines(updated_lines)
            os.remove(patch_file_path)
            return f"Successfully edited the file {relative_file_path} from line {start_line} to {end_line}"
        else:
            os.remove(patch_file_path)
            return f"Error executing command. Error message: {summarizer(stdout_output + stderr_output)}. Please read this error message carefully, reopen the file using open_file tool then try to fix the generated code."

class OpenFileToolForGeneratorArgs(BaseModel):
    relative_file_path: str = Field(..., description="The relative path of the file we want to open")
    keywords: List[str] = Field(..., description="The list of keywords you want to search in the file, it's should be a single word like grpc but not grpcio.grpc")
    start_line: Optional[int] = Field(..., description="The starting line number of the file we want to open")
    end_line: Optional[int] = Field(..., description="The ending line number of the file we want to open")

class OpenFileToolForGenerator(BaseTool):
    """
    Tool for opening a file inside a repository.

    Args:
        path (str): The path to the repository.
        language (str): The language of the file.

    Attributes:
        name (str): The name of the tool.
        description (str): The description of the tool.
        args_schema (class): The schema for the tool's arguments.
        path (str): The path to the repository.

    Methods:
        _run(relative_file_path: str, max_new_line: int = 500) -> str:
            Runs the tool to open the specified file.

    """

    name = "open_file"
    description = """Useful when you want to open a file inside a repo for editing. If you have a keyword in mind, you can use it to search the keyword in the file. Otherwise, you can specify the start and end line to view the content of the file. The number of lines to show is limited at 150 for example (100:250).
    """
    args_schema = OpenFileToolForGeneratorArgs
    path = ""
    language = ""
    parser: Optional[Callable] = None
    
    def __init__(self, path, language=None):
        super().__init__()
        self.path = path
        self.parser = get_parser(language)
        self.language = language
    
    def _run(self, relative_file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, keywords: List[str] = [], preview_size: int = 10, max_num_result: int = 5):
        """
        Opens the specified file and returns its content.

        Args:
            relative_file_path (str): The relative path to the file.
            max_new_line (int, optional): The maximum number of lines to include in the returned content. Defaults to 500.

        Returns:
            str: The content of the file.

        """
        abs_path = os.path.join(self.path, relative_file_path)
        if not os.path.exists(abs_path):
            return "File not found, please check the path again"
        
        if len(keywords) == 0 and start_line is None and end_line is None:
            return "Please specify the keyword or start and end line to view the content of the file."
        
        try:
            if start_line is not None and end_line is not None:
                if end_line - start_line > 150:
                    return f"The number of lines to show is limited at 150, the requested number of lines is {end_line - start_line}, please specify the start and end line again (smaller |end_line-start_line|) or using keyword instead."
                source = open(abs_path, "r").read()
                lines = source.split("\n")
                source = "\n".join(lines[start_line:end_line]) 
            else:
                line_idx = []
                returned_source = []
                if osp.isfile(abs_path):
                    source = open(abs_path, "r").read()
                else:
                    return "Your path is not a file, please check the path again. Use the get_folder_structure tool to see the structure of the folder"
                lines = source.split("\n")
                out_str = "The content of " + relative_file_path.replace(self.path, "") + " is: \n"
                for keyword in keywords:
                    out_str += f"Results for keyword: {keyword}\n"
                    line_idx = []
                    returned_source = []
                    source = open(abs_path, "r").read()
                    lines = source.split("\n")
                    for i, line in enumerate(lines):
                        if keyword in line:
                            line_idx.append(i)
                            
                line_idx = line_idx[:max_num_result]
                line_ranges = [None for _ in line_idx]
                # get class, func list
                root_node = parse_code(source, self.language).root_node
                function_list = self.parser.get_function_list(root_node)
                class_list = self.parser.get_class_list(root_node)
                
                for func in function_list:

                    for i, idx in enumerate(line_idx):
                        if func.start_point[0] <= idx <= func.end_point[0]:
                            line_ranges[i] = (func.start_point[0], func.end_point[0]+1)
                
                for class_ in class_list:

                    for i, idx in enumerate(line_idx):
                        if class_.start_point[0] <= idx <= class_.end_point[0]:
                            line_ranges[i] = (class_.start_point[0], class_.end_point[0]+1)
                        
                    
                if len(line_idx) == 0:
                    return "No keyword found in the file, please check the keyword again or use the start and end line instead"
                else:
                    import_source = add_num_line("\n".join(lines[:80]), 1)
                    for i in range(len(line_idx)):
                        if line_ranges[i] is None:
                            expanded_source = "\n".join(lines[max(0, line_idx[i]-preview_size):min(len(lines), line_idx[i]+preview_size)])
                            expanded_source = add_num_line(expanded_source, max(1, line_idx[i]-preview_size)+1)
                        else:
                            expanded_source = "\n".join(lines[max(0, line_ranges[i][0]-preview_size):min(len(lines), line_ranges[i][1]+preview_size)])
                            expanded_source = add_num_line(expanded_source, max(1, line_ranges[i][0]-preview_size)+1)
                        returned_source.append(expanded_source)
                    return "The content of " + relative_file_path.replace(self.path, "") + " is: \n" + import_source + "\n" + "\n".join(returned_source)
        except FileNotFoundError:
            return "File not found, please check the path again"
        except TypeError:
            source = open(abs_path, "r").read()
        source = add_num_line(source, start_line)
        return "The content of " + relative_file_path.replace(self.path, "") + " is: \n" + source