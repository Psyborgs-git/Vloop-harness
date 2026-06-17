import main
import threading
import time
t = threading.Thread(target=main.serve, daemon=True)
t.start()
time.sleep(2)
print("Finished waiting")
