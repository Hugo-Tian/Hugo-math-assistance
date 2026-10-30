# 向量与线性运算

$n$ 维向量是由 $n$ 个数组成的有序数组 $\mathbf{u}=(u_1,u_2,\dots,u_n)$。两个同维向量相加时逐分量相加：$\mathbf{u}+\mathbf{v}=(u_1+v_1,\dots,u_n+v_n)$；数乘时每个分量乘以同一个数：$k\mathbf{u}=(ku_1,\dots,ku_n)$。

向量的加法与数乘统称线性运算，满足交换律、结合律以及数乘对加法的分配律 $k(\mathbf{u}+\mathbf{v})=k\mathbf{u}+k\mathbf{v}$。形如 $k_1\mathbf{v}_1+k_2\mathbf{v}_2+\dots+k_m\mathbf{v}_m$ 的向量称为这些向量的线性组合。

例：$\mathbf{u}=(1,2)$，$\mathbf{v}=(3,-1)$，则 $2\mathbf{u}+\mathbf{v}=(2+3,\,4-1)=(5,3)$。易错点：不同维数的向量不能相加。

# 向量的几何意义

二维、三维向量可以看作从原点出发的有向线段。向量加法满足平行四边形法则：以 $\mathbf{u}$、$\mathbf{v}$ 为邻边作平行四边形，对角线即 $\mathbf{u}+\mathbf{v}$。数乘 $k\mathbf{u}$ 把向量伸缩 $|k|$ 倍，$k<0$ 时方向反转。

所有分量为零的向量称为零向量，记作 $\mathbf{0}$，它是加法的单位元：$\mathbf{u}+\mathbf{0}=\mathbf{u}$。

# 内积与长度

$\mathbb{R}^n$ 中两个向量的内积（点积）定义为 $\mathbf{u}\cdot\mathbf{v}=u_1v_1+u_2v_2+\dots+u_nv_n$，结果是一个数，而不是向量。内积满足对称性 $\mathbf{u}\cdot\mathbf{v}=\mathbf{v}\cdot\mathbf{u}$ 和线性性。

向量的长度（模）为 $\|\mathbf{u}\|=\sqrt{\mathbf{u}\cdot\mathbf{u}}$。例：$\mathbf{u}=(1,2,2)$ 时 $\mathbf{u}\cdot\mathbf{u}=9$，所以 $\|\mathbf{u}\|=3$。长度为 1 的向量称为单位向量，非零向量除以自身长度即可单位化。

# 正交与夹角

两个非零向量的夹角 $\theta$ 满足 $\cos\theta=\dfrac{\mathbf{u}\cdot\mathbf{v}}{\|\mathbf{u}\|\,\|\mathbf{v}\|}$。当 $\mathbf{u}\cdot\mathbf{v}=0$ 时称两向量正交（垂直）。

例：求 $k$ 使 $(1,k,2)$ 与 $(3,1,-1)$ 正交。由 $3+k-2=0$ 得 $k=-1$。易错点：判断正交只需内积为零，不必先求长度。
