import TopNav from './shell/TopNav';

/**
 * Every page renders ``<Sidebar />`` itself, so keeping that one import lets the left sidebar become the horizontal menu bar
 * without touching those pages. The bar is fixed to the top; ``responsive.css`` removes the 260px offset they still reserve.
 */
const Sidebar = () => <TopNav />;

export default Sidebar;
