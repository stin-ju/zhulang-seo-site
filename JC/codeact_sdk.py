class CodeActSDK:
    def __init__(self): pass
    async def submit_result(self, **kw):
        print(f"[CodeAct SDK] {kw.get('status','ok')} {kw.get('message','')}")
