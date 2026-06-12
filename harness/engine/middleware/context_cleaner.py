import re

class ContextCleaner:
    """
    Middleware that processes stdout/stderr streams before they enter the LLM's memory window.
    Removes ANSI formatting, squashes loading bars (carriage returns), and truncates massive stack traces.
    """
    
    # ANSI Stripper: Destroy all terminal color and formatting codes.
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    def __init__(self, max_lines=10000, keep_first=50, keep_last=100):
        self.max_lines = max_lines
        self.keep_first = keep_first
        self.keep_last = keep_last

    def clean(self, raw_output: str) -> str:
        if not raw_output:
            return ""
            
        # 1. Squash Carriage Returns (The Loading Bar Fix)
        # We split by \n to process line by line, but inside each line, a \r without \n overwrites previous content
        lines = raw_output.split('\n')
        squashed_lines = []
        for line in lines:
            if '\r' in line:
                # The last segment after \r is the final state of that line
                line = line.split('\r')[-1]
            squashed_lines.append(line)
            
        squashed_output = '\n'.join(squashed_lines)
        
        # 2. Strip ANSI
        stripped_output = self.ANSI_ESCAPE.sub('', squashed_output)
        
        # 3. Truncation Heuristics
        final_lines = stripped_output.split('\n')
        if len(final_lines) > self.max_lines:
            truncated = final_lines[:self.keep_first]
            truncated.append(f"\n...[{len(final_lines) - self.keep_first - self.keep_last} lines truncated]...\n")
            truncated.extend(final_lines[-self.keep_last:])
            return '\n'.join(truncated)
            
        return stripped_output
