// public/client.js

const roomInput        = document.getElementById("roomInput");
const joinBtn          = document.getElementById("startBtn");
const startAvatarBtn   = document.getElementById("startAvatarBtn");
const avatarVideo      = document.getElementById("avatarVideo");

let ws;
let pc;

// ICE servers configuration (you can add TURN here later)
const ICE_CONFIG = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" }
  ]
};

//
// 1) Join & establish initial PeerConnection (no local tracks)
//
joinBtn.onclick = async () => {
  const room = roomInput.value.trim();
  if (!room) {
    return alert("Please enter a room name");
  }
  joinBtn.disabled = true;

  // open WebSocket to signaling server
  ws = new WebSocket(`ws://${location.host}/ws`);

  // create RTCPeerConnection
  pc = new RTCPeerConnection(ICE_CONFIG);

  // handle new incoming tracks (the avatar will appear here)
  pc.ontrack = ({ streams: [stream] }) => {
    avatarVideo.srcObject = stream;
  };

  // send any ICE candidates to the server
  pc.onicecandidate = ({ candidate }) => {
    if (candidate) {
      ws.send(JSON.stringify({
        action:    "ice-candidate",
        candidate
      }));
    }
  };

  // signaling message handler
  ws.onmessage = async ({ data }) => {
    const msg = JSON.parse(data);

    switch (msg.action) {
      case "ready":
      case "renegotiate":
        // either initial ready or after adding avatar track:
        // create & send an offer
        {
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          ws.send(JSON.stringify({
            action: "offer",
            sdp:    pc.localDescription.sdp,
            type:   pc.localDescription.type
          }));
        }
        break;

      case "offer":
        // server wants us to answer
        await pc.setRemoteDescription(
          new RTCSessionDescription(msg)
        );
        {
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          ws.send(JSON.stringify({
            action: "answer",
            sdp:    pc.localDescription.sdp,
            type:   pc.localDescription.type
          }));
        }
        break;

      case "answer":
        // server answered our offer
        await pc.setRemoteDescription(
          new RTCSessionDescription(msg)
        );
        break;

      case "ice-candidate":
        // add ICE from server / other peer
        try {
          await pc.addIceCandidate(msg.candidate);
        } catch (e) {
          console.warn("Failed to add ICE Candidate:", e);
        }
        break;

      default:
        console.warn("Unhandled WS message:", msg);
    }
  };

  // once WS is open, join the room
  ws.onopen = () => {
    ws.send(JSON.stringify({ action: "join", room }));
  };
};

//
// 2) Trigger MuseTalk & renegotiate to get the avatar track
//
startAvatarBtn.onclick = () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return alert("You must join a room first");
  }
  // tell the server to start MuseTalk and add the video track
  ws.send(JSON.stringify({ action: "start-avatar" }));
};
