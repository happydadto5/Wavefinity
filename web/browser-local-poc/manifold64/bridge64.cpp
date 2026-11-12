#include <emscripten/bind.h>
#include <emscripten/val.h>
#include <manifold/manifold.h>
using namespace emscripten;
using namespace manifold;
Manifold make(val verts, val faces) {
 MeshGL64 mesh; mesh.numProp=3;
 mesh.vertProperties=convertJSArrayToNumberVector<double>(verts);
 auto f=convertJSArrayToNumberVector<uint32_t>(faces);
 mesh.triVerts.assign(f.begin(), f.end());
 Manifold m(mesh); if (m.Status()!=Manifold::Error::NoError) throw std::runtime_error("Invalid input manifold"); return m;
}
val output(const Manifold &m) {
 if(m.Status()!=Manifold::Error::NoError) throw std::runtime_error("Boolean failed");
 auto mesh=m.GetMeshGL64(); val v=val::object();
 v.set("vertices",val(typed_memory_view(mesh.vertProperties.size(),mesh.vertProperties.data())).call<val>("slice"));
 std::vector<uint32_t> f(mesh.triVerts.begin(),mesh.triVerts.end());
 v.set("faces",val(typed_memory_view(f.size(),f.data())).call<val>("slice")); return v;
}
Manifold add(const Manifold&a,const Manifold&b){return a+b;}
Manifold sub(const Manifold&a,const Manifold&b){return a-b;}
Manifold intersect(const Manifold&a,const Manifold&b){return a^b;}
EMSCRIPTEN_BINDINGS(bridge) { class_<Manifold>("Solid").function("mesh",&output).function("add",&add).function("sub",&sub).function("intersect",&intersect); function("make",&make); }
