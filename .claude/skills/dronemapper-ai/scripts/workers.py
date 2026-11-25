import json, traceback
OUT = r"C:\t\monitor\workers.json"
try:
    import Metashape
    c = Metashape.NetworkClient(); c.connect("127.0.0.1")
    ws = c.workerList()
    bl = c.batchList()
    json.dump({"workers": ws, "batches": bl}, open(OUT, "w"), default=str)
except Exception:
    open(OUT, "w").write(traceback.format_exc())
