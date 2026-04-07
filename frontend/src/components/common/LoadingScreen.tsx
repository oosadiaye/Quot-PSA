import React from 'react';
import { Spin } from 'antd';
import './LoadingScreen.css';

interface LoadingScreenProps {
    message?: string;
    fullScreen?: boolean;
}

const LoadingScreen: React.FC<LoadingScreenProps> = ({
    message = 'Loading...',
    fullScreen = true
}) => {
    return (
        <div className={`loading-screen ${fullScreen ? 'full-screen' : ''}`}>
            <Spin size="large" description={message} />
        </div>
    );
};

export default LoadingScreen;
