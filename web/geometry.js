/**
 * Geometric primitives, mirroring src/movement/geometry.py.
 *
 * Canonical landmarks divide x by image width and y by image height, so the
 * raw space is anisotropic and any angle computed in it is wrong by the aspect
 * ratio. On 1280x720 that compresses horizontal distances by 0.5625.
 *
 * This is not a theoretical concern. The same mistake was made twice during
 * development, the second time in an analysis written *after* the Python
 * module that exists to prevent it. An elbow angle computed here without the
 * correction would disagree with the Python gesture detector, and the two
 * would accept different arm positions.
 *
 * Everything works in image heights: both axes divided by image height.
 */

/** Assumed when a pose frame does not carry its image size. */
export const DEFAULT_ASPECT = 16 / 9;

export function aspectRatio(pose) {
  if (pose.image_width && pose.image_height) {
    return pose.image_width / pose.image_height;
  }
  return DEFAULT_ASPECT;
}

/** Isotropic position of a canonical landmark, or null if absent. */
export function pointOf(pose, name, aspect) {
  const landmark = pose.landmarks[name];
  if (!landmark) return null;
  return [landmark.x * aspect, landmark.y];
}

/**
 * Interior angle at `vertex` in degrees, 0 to 180, or null if degenerate.
 */
export function angleAt(first, vertex, second) {
  const ax = first[0] - vertex[0];
  const ay = first[1] - vertex[1];
  const bx = second[0] - vertex[0];
  const by = second[1] - vertex[1];
  const magnitude = Math.hypot(ax, ay) * Math.hypot(bx, by);
  if (magnitude <= 1e-9) return null;
  const cosine = (ax * bx + ay * by) / magnitude;
  return (Math.acos(Math.max(-1, Math.min(1, cosine))) * 180) / Math.PI;
}
