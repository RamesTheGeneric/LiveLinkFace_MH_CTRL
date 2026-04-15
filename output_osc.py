from pythonosc import udp_client
import numpy as np

names = [
    "/cheekPuffLeft", # 0
    "/cheekPuffRight", # 1
    "/cheekSuckLeft", # 2
    "/cheekSuckRight", # 3
    "/jawOpen", # 4 
    "/jawForward", # 5 
    "/jawLeft", # 6 
    "/jawRight", # 7 
    "/noseSneerLeft", # 8 ~
    "/noseSneerRight", # 9 ~
    "/mouthFunnel",  # 10
    "/mouthPucker", # 11
    "/mouthLeft",  # 12
    "/mouthRight", # 13
    "/mouthRollUpper",  # 14
    "/mouthRollLower", # 15
    "/mouthShrugUpper", # 16
    "/mouthShrugLower", # 17
    "/mouthClose", # 18
    "/mouthSmileLeft", # 19
    "/mouthSmileRight", # 20
    "/mouthFrownLeft", # 21
    "/mouthFrownRight", # 22
    "/mouthDimpleLeft", # 23 ~  Baked into sranipal smile???
    "/mouthDimpleRight", # 24 ~ Baked into sranipal smile???
    "/mouthUpperUpLeft", # 25
    "/mouthUpperUpRight", # 26
    "/mouthLowerDownLeft", # 27
    "/mouthLowerDownRight", # 28
    "/mouthPressLeft", # 29  ~
    "/mouthPressRight", # 30  ~
    "/mouthStretchLeft", # 31  ~
    "/mouthStretchRight", # 32  ~
    "/tongueOut", # 33
    "/tongueUp", # 34
    "/tongueDown", # 35
    "/tongueLeft", # 36
    "/tongueRight", # 37
    "/tongueRoll", # 38
    "/tongueSquish", # 39  ~
    "/tongueFlat",  # 40  ~
    "/tongueTwistLeft", # 41  ~ 
    "/tongueTwistRight" # 42  ~
]

def sr_to_bbl(sr_jawOpen: float, sr_apeShape: float):
    """
    Convert SR values back to BBL blendshape values.

    Inverse of bbl_to_sr():
    - When sr_jawOpen = 0, sr_apeShape = 1 → bbl_mouthClose = bbl_jawOpen
    - When sr_jawOpen = 1, sr_apeShape = 0 → bbl_mouthClose = 0
    - Interpolates linearly between those states.

    Args:
        sr_jawOpen (float): SR jaw open (0–1)
        sr_apeShape (float): SR ape shape (0–1)
        bbl_jawOpen (float): Reference BBL jaw open value (default=1.0)

    Returns:
        tuple: (bbl_jawOpen, bbl_mouthClose)
    """
    sum = sr_jawOpen + sr_apeShape
    bbl_jawOpen = max(sum, 0)

    bbl_mouthClose = max(sum*sr_apeShape, 0)
    return bbl_jawOpen, bbl_mouthClose

def normalize_and_clip(x: float, min_val: float, max_val: float) -> float:
    """
    Normalize a value from [0, 1] into [0.25, 1],
    then clip the result to [0, 1].
    """
    # Normalize 0–1 → 0.25–1
    y = float((x - min_val) / (max_val - min_val))
    y = max(0.0, min(1.0, y))
    return y
    # Clip to 0–1
    #return max(0.0, min((1.0, y)))

class OSCClient:
    def __init__(self, ip: str, port: int):
        self.c = udp_client.SimpleUDPClient(ip, port)

    def send_msgs(self, c):
        lipFunnel = (c['mouthFunnelUL'] + c['mouthFunnelUR'] + c['mouthFunnelDL'] + c['mouthFunnelDR']) / 4  # Average of both lip funnel values
        mouthPucker = (c['mouthLipsPurseUL'] + c['mouthLipsPurseUR'] + c['mouthLipsPurseDL'] + c['mouthLipsPurseDR'] + c['mouthLipsTowardsUL'] + c['mouthLipsTowardsUR'] + c['mouthLipsTowardsDL'] + c['mouthLipsTowardsDR']) / 8  # Average of both mouth pucker values
        mouthRollUpper = (c['mouthUpperLipRollInL'] + c['mouthUpperLipRollInR']) / 2  # Average of all upper lip roll values
        mouthRollLower = (c['mouthLowerLipRollInL'] + c['mouthLowerLipRollInR']) / 2  # Average of all lower lip roll values
        mouthPressLeft = (c['mouthPressUL'] + c['mouthPressDL']) / 2  # Average of left mouth press values
        mouthPressRight = (c['mouthPressUR'] + c['mouthPressDR']) / 2  # Average of right mouth press values
        tongueOut = 0
        mouthClose = (c['mouthLipsTogetherUL'] + c['mouthLipsTogetherUR'] + c['mouthLipsTogetherDL'] + c['mouthLipsTogetherDR']) / 4  # Average of both mouth close values
        self.c.send_message("/jawRight", float(c['jawRight']))
        self.c.send_message("/jawLeft", float(c['jawLeft']))
        self.c.send_message("/jawForward", float(c['jawFwd']))      
        self.c.send_message("/jawOpen", float(c['jawOpen']))       
        self.c.send_message("/noseSneerRight", float(c['noseWrinkleR']))
        self.c.send_message("/noseSneerLeft", float(c['noseWrinkleL']))
        self.c.send_message("/mouthClose", float(normalize_and_clip(mouthClose, 0.0, 1.0)))
        self.c.send_message("/mouthLeft", float(c['mouthLeft']))
        self.c.send_message("/mouthRight", float(c['mouthRight']))
        self.c.send_message("/mouthUpperUpRight", float(c['mouthUpperLipRaiseR']))
        self.c.send_message("/mouthUpperUpLeft", float(c['mouthUpperLipRaiseL']))
        self.c.send_message("/mouthLowerDownRight", float(c['mouthLowerLipDepressR']))
        self.c.send_message("/mouthLowerDownLeft", float(c['mouthLowerLipDepressL']))
        self.c.send_message("/mouthPressRight", float(mouthPressRight))
        self.c.send_message("/mouthPressLeft", float(mouthPressLeft))
        self.c.send_message("/mouthStretchRight", float(c['mouthStretchR']))
        self.c.send_message("/mouthStretchLeft", float(c['mouthStretchL']))
        self.c.send_message("/mouthFunnel", float(lipFunnel))
        self.c.send_message("/mouthPucker", float(mouthPucker))
        self.c.send_message("/mouthSmileRight", float(c['mouthCornerPullR']))
        self.c.send_message("/mouthSmileLeft", float(c['mouthCornerPullL']))    
        self.c.send_message("/mouthFrownRight", float(c['mouthCornerDepressR']))
        self.c.send_message("/mouthFrownLeft", float(c['mouthCornerDepressL']))
        self.c.send_message("/mouthDimpleLeft", float(c['mouthDimpleL']))
        self.c.send_message("/mouthDimpleRight", float(c['mouthDimpleR']))
        self.c.send_message("/cheekPuffRight", float(c['mouthCheekBlowR']))
        self.c.send_message("/cheekPuffLeft", float(c['mouthCheekBlowL']))    
        self.c.send_message("/cheekSuckRight", float(c['mouthCheekSuckR']))   
        self.c.send_message("/cheekSuckLeft", float(c['mouthCheekSuckL']))
        self.c.send_message("/mouthRollUpper", float(mouthRollUpper))
        self.c.send_message("/mouthRollLower", float(mouthRollLower))     
        self.c.send_message("/mouthShrugUpper", float(c['mouthUp']))
        self.c.send_message("/mouthShrugLower", float(c['mouthDown']))   
        self.c.send_message("/tongueOut", float(tongueOut))
        self.c.send_message("/tongueLeft", float(0))
        self.c.send_message("/tongueRight", float(0))
        self.c.send_message("/tongueUp", float(0))
        self.c.send_message("/tongueDown", float(0))
        self.c.send_message("/tongueRoll", float(0))
        # twist lr

        # flat squish
        







            
        
