import "./brand.css";

const emblem = `${import.meta.env.BASE_URL}favicon.svg`;

export function BrandEmblem() {
  return <img className="grans-emblem" src={emblem} width={48} height={48} alt="" />;
}

export function Brand({ className }: { className: string }) {
  return (
    <div className={`grans-brand ${className}`}>
      <BrandEmblem />
      <div className="grans-copy">
        <span className="grans-company">Grans Enterprise</span>
        <strong className="grans-product">Identity<span>Ops</span></strong>
        <span className="grans-subtitle">Identity &amp; Access Management Platform</span>
      </div>
    </div>
  );
}

export function BrandCredit() {
  return <p className="grans-credit">Engineered by Gabriel Grans</p>;
}
