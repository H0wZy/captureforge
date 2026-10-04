# BodyForge: how to film a clip

The quality of a clip is decided at the camera. BodyForge tracks one person from one fixed phone camera with MediaPipe
Pose; it is good at slow, in-place gestures and weaker at fast, hidden or crowded ones. Any Android or other phone
works, and so does a webcam. No iPhone, depth sensor or LiDAR is needed.

BodyForge warns you about the most common problems before the solve (low frame rate, body out of the picture, low
confidence, several people), and the quality report shows which frame ranges were weak.

> **Responsible use.** Film yourself, or someone who has agreed to it. Do not capture or animate a real person without
> their explicit consent. Read [POLICY.md](../POLICY.md). Keep the videos outside the repository.

## The basics (every clip)

- **Camera**: phone on a tripod or a stable surface, landscape or portrait, **not moving**. Lens at about chest height,
  pointing straight at the person. A slight angle (up to about 30 degrees) is fine; side-on views lose depth.
- **Framing**: the whole body from head to feet in view for the whole take, with some room around the hands when they
  go up or out. Do not crop the feet.
- **Frame rate**: **30 fps or more**; use **60 fps** for fast moves (dance). Lock the exposure and turn off beauty
  filters and stabilisation if the phone has them.
- **Light**: bright, even light (a window or outdoor shade); avoid backlight. Fast moves need strong light so the
  shutter can be short and the picture stays sharp.
- **Background and clothes**: a plain background and clothes that contrast with it. Fitted clothes, not baggy; sleeves
  that do not hide the elbows; shoes that are not the colour of the floor. Avoid a person-shaped poster behind you.
- **Neutral start**: begin every take **standing still for 1.5 to 2 seconds**, arms relaxed at the sides, facing the
  camera. BodyForge measures your proportions, the up direction and the floor from that pose (set the length in
  "Neutral s"). Without it the rig's standard proportions are used and you get a warning.
- **One person** in the picture. If a second person is seen, the most prominent one is tracked and you get a warning.
- Keep the file outside the repository; BodyForge writes the landmarks, the report and the filmstrip next to it.

## The four clips

### 1. Hands up (surrender), required, the easy one

Stand still, then raise both hands slowly above the head with open palms to the camera and hold for a second. Keep the
elbows visible. Good for checking the whole chain. Tip: leave a hand's width of picture above the raised hands.

### 2. Frisk (hands on), required

Turn the hand tracking on (**Hands and fingers**; it needs the hand model from **Install helper**). Face the camera with
the arms out to the sides, palms down, then let them be patted down. Keep the hands **in front of the body, not behind
it**, and avoid long overlaps of both hands on the torso: the hand model loses a hand that is covered, and the fingers
then hold or relax to rest. Film the actor and the "frisker" as two separate takes; BodyForge tracks one person.

### 3. Riding a motorcycle, best effort

Sit on a parked bike or a chair in the same pose, camera at the side-front, with **both arms and at least one leg
fully visible**. The hidden leg and the seat make the feet unreliable: turn the **foot lock off** (per foot or per frame
range) and, if needed, pose the feet by hand afterwards. Expect the hips height to be approximate while seated.

### 4. Dance, best effort

Use **60 fps**, strong light, tight clothes and a clear floor; stay in place and inside the picture for the whole move.
Switch on **Keep video frame rate** to key at 60 fps. Fast arms blur: the report lists low-confidence ranges, which you
can trim or fix by hand. For a looping dance, end near the starting pose and use **Close loop**.

## Known limits

- One person, one fixed camera, mostly in place. World travel, camera moves and jumps are not recovered.
- Depth is the weak axis of single-camera tracking: arms pointing at the camera are noisy. Film from the front, or
  turn the move so it happens across the picture when you can.
- The foot lock is a heuristic. Jumps, deep crouches and seated poses need it off.
- Fingers are curl and wrist twist only, not finger-accurate hand pose.
- Hidden or cropped parts are held or bridged from the good frames around them and are flagged in the report.

## After the take

1. **Video to body** (or load a landmark file), then **Clean up**, then **Report** and look at the filmstrip.
2. Fix what the report flags: trim bad ends, switch the foot lock off where it hurt, mirror if the move was filmed
   the wrong way round.
3. **Export for Unity**, and import it as a Humanoid clip with the character's own avatar (see the quickstart in
   `specs/001-bodyforge-v1/quickstart.md`).
