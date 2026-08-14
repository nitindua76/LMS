from livekit import api as lk_api

print("--- ParticipantInfo fields ---")
print([f.name for f in lk_api.ParticipantInfo.DESCRIPTOR.fields])
print()
print("--- TrackInfo fields ---")
print([f.name for f in lk_api.TrackInfo.DESCRIPTOR.fields])
print()
print("--- ParticipantInfo.state enum values ---")
for f in lk_api.ParticipantInfo.DESCRIPTOR.fields:
    if f.name == "state":
        print([v.name for v in f.enum_type.values])
print()
# check for any bandwidth/stats-related fields anywhere
import livekit.protocol.models as models_pb
print("--- models_pb module contents (classes) ---")
print([n for n in dir(models_pb) if not n.startswith("_")])
