export const intersects = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
export const selectedIdsForRect = (rect, clips) => clips.filter((clip) => intersects(rect, clip)).map((clip) => clip.id);
export const formatTime = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
