/**
 * `MeshSurfaceSampler.setRandomGenerator` exists in the three 0.180 runtime
 * (examples/jsm/math/MeshSurfaceSampler.js) but is missing from @types/three
 * 0.180. Declared here rather than cast away, so a future types release that
 * adds it — or a runtime that drops it — surfaces as a compile error.
 */
import 'three/examples/jsm/math/MeshSurfaceSampler.js';

declare module 'three/examples/jsm/math/MeshSurfaceSampler.js' {
  interface MeshSurfaceSampler {
    setRandomGenerator(randomFunction: () => number): this;
  }
}
